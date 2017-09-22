#
# (c) Copyright 2015-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
#
import logging
import warnings

from dogpile.cache import make_region
from dogpile.cache.util import sha1_mangle_key
from keystoneclient.auth.identity import v3
from keystoneclient import session, exceptions
from keystoneclient.v3 import client as ksclient3
from requests.packages.urllib3.exceptions import InsecureRequestWarning

from bll.api import USER_AGENT
from bll.common.exception import BllAuthenticationFailedException
from bll.common.util import get_conf, start_cache_cleaner

LOG = logging.getLogger(__name__)

# There are two separate caches being created.
#
# The "static" cache contains items that are unlikely to change while the BLL
# is run and whose number of entries is not going to continue to grow.  These
# items are not specific to the logged in user.
#
# The "session" cache contains items that are tied to keystone sessions,
# and the region's timeout is set to match keystone's (4 hours).   After
# the expiration time is hit, dogpile will not return the value from the cache,
# but will trigger the function to run and re-obtain its values.  The
# in-memory backends supplied by dogpile do not actually delete expired
# entries from the cache, so a separate thread is spawned to periodically
# clean these up to avoid runaway memory usage.
#
static = make_region(key_mangler=sha1_mangle_key).configure(
    'dogpile.cache.memory')

cache = {}
cache_expiration = get_conf('cache_expiration', 14400)   # 4 hours
# session = make_region(key_mangler=sha1_mangle_key).configure(
session_cache = make_region().configure(
    'dogpile.cache.memory',
    expiration_time=cache_expiration,
    arguments={"cache_dict": cache})

start_cache_cleaner(cache, cache_expiration, "SessionCacheCleaner")


def login(username, password, domain='Default'):
    """
    Perform the initial login to the BLL, using the given credentials.  This
    uses the "normal" keystone workflow of:
    - Connecting to keystone and obtain an unscoped token (not scoped to any
         particular project or domain)
    - Get a list of projects available to the given user
    - Select a project, and connect to keystone again (with the unscoped token)
         to receive a project-scoped token.
    Returns a keystone auth_ref, which contains the token, expiration, and
            other info about the authentication

    This function is primarily used in the initial login UI screen, but is
    also used by the deploy service
    """

    LOG.debug("Obtaining unscoped token for user %s", username)

    auth = v3.Password(auth_url=get_auth_url(),
                       username=username,
                       password=password,
                       user_domain_name=domain,
                       unscoped=True)
    unscoped_session = session.Session(auth=auth, user_agent=USER_AGENT,
                                       verify=verify_https())
    try:
        unscoped_token = unscoped_session.get_token()
    except Exception as e:
        raise BllAuthenticationFailedException(
            "User is not authorized on the %s domain: [%s]" % (domain, str(e)))
    return get_appropriate_auth_ref(unscoped_token)


def validate(token):
    return get_appropriate_auth_ref(token) is not None


@session_cache.cache_on_arguments()
def get_appropriate_auth_ref(token):
    """
    The incoming token does not indicate which project it is for.  Therefore
    we find the appropriate project (normally one for which the token's user
    has admin privilege for) and return an auth_ref.  The auth_ref can then
    be used to instantiate a Keystone object without requiring an additional
    round-trip to authenticate against keystone
    """
    LOG.debug("Obtaining unscoped keystone client with token")
    auth = v3.Token(auth_url=get_auth_url(), token=token, unscoped=True)
    sess = session.Session(auth=auth, user_agent=USER_AGENT,
                           verify=verify_https())
    ks = ksclient3.Client(session=sess, user_agent=USER_AGENT)

    project_list = [t.name for t in ks.projects.list(user=sess.get_user_id())]
    auth_ref = _find_appropriate_project(token, project_list)

    # Verify that the user is a 'cloud admin', i.e. that they have the
    # admin role on the default domain.  Domain roles are only valid in
    # keystone v3, so make sure to use an appropriate auth URL
    role_names = []

    try:
        ks = ksclient3.Client(token=token,
                              auth_url=get_auth_url(),
                              domain_name='default',
                              verify=verify_https())
        role_names = ks.auth_ref.role_names

    except Exception:
        raise BllAuthenticationFailedException(
            "User is not authorized on the default domain")

    if 'admin' not in role_names:
        raise BllAuthenticationFailedException(
            "User is not an admin of the default domain")

    return auth_ref


def _find_appropriate_project(token, project_list):

    # sort and order the list so that admin is the first project to try,
    # since that is the one that most administrators have the admin role in
    if 'admin' not in project_list:
        raise BllAuthenticationFailedException(
            "User does not have access to the admin project")

    # Users must have the admin or monasca-user role on the admin project
    # in order to manage monasca entities
    auth_ref = _get_auth_ref(token, 'admin')
    if 'admin' in auth_ref.role_names:
        return auth_ref

    if 'monasca-user' not in auth_ref.role_names:
        raise BllAuthenticationFailedException(
            "User does not have the proper role in the admin project")

    # Since we have already authorized against the admin project, there is
    # no need to do it again in the following loop
    projects = sorted(project_list)
    projects.remove('admin')

    # We do not know which project the token has admin role on,
    # so we have to check against the list of projects
    for project in projects:
        auth_ref = _get_auth_ref(token, project)

        if 'admin' in auth_ref.role_names:
            return auth_ref

    # If we got here, we do not have admin access
    raise BllAuthenticationFailedException(
        "User does not have admin access")


@session_cache.cache_on_arguments()
def _get_auth_ref(token, project_name, domain_name='Default'):
    """
    Return auth ref for the given token and project_name
    """
    LOG.debug("Obtaining scoped keystone client with token, project %s",
              project_name)

    auth = v3.Token(auth_url=get_auth_url(),
                    project_name=project_name,
                    project_domain_name=domain_name,
                    token=token)
    project_session = session.Session(auth=auth,
                                      verify=verify_https(),
                                      user_agent=USER_AGENT)

    # Trigger the generation of the new token
    project_session.get_auth_headers()
    return project_session.auth.auth_ref


def get_auth_url(version='v3'):
    """
    Get default url from config file
    :return:
    """

    url = get_conf("keystone.private_url")
    if url is None:
        url = '%s://%s:%d' % (
            get_conf("keystone.protocol"),
            get_conf("keystone.host"),
            get_conf("keystone.public_port"))

    return '%s/%s' % (url, version)


@session_cache.cache_on_arguments()
def _get_session(token):
    """
    Return v3 session for token
    """
    auth_ref = get_appropriate_auth_ref(token)

    auth = v3.Token(auth_url=get_auth_url(),
                    project_id=auth_ref.project_id,
                    token=token)
    return session.Session(auth=auth, user_agent=USER_AGENT,
                           verify=verify_https())


def _get_domain_session(token, domain_name=None):
    """
    Return v3 session for token
    """
    domain_name = domain_name or 'default'
    auth = v3.Token(auth_url=get_auth_url(),
                    domain_id=domain_name,
                    token=token)
    return session.Session(auth=auth, user_agent=USER_AGENT,
                           verify=verify_https())


warnings_filtered = False


def verify_https():

    global warnings_filtered

    # Perform SSL verification unless explicitly configured otherwise
    verify = not get_conf("insecure")
    # If SSL verification is turned off, just log the insecure warning once
    #   instead of repeating it ad nauseum.  Use warnings_filtered
    #   boolean to avoid repeatedly adding a filter to the warnings system
    if not verify and not warnings_filtered:
        warnings.filterwarnings("once", category=InsecureRequestWarning)
        warnings_filtered = True

    return verify


class TokenHelpers:

    def __init__(self, token):
        self.token = token

    def get_user_token(self):
        """
        Return the original token that the user authenticated with
        """
        return self.token

    def get_token_for_project(self, project_name):
        """
        Get the token for a specific project.  This is needed in places
        where self.token corresponds to a project other than the one that
        is needed by the caller.
        """
        return _get_auth_ref(self.token, project_name).auth_token

    @static.cache_on_arguments()
    def get_endpoints(self, service_type,
                      region=None,
                      endpoint_type=get_conf("services.endpoint_type",
                                             default="internalURL")):
        """
        Returns a list of unique internal service endpoint(s) for the given
        service type and region.  If no region is specified, keystone will
        capture the unique endpoints across regions.  If two regions
        share the same URL, then only one will be returned.  For example,
        if keystone contains 3 endpoints for service x:
           [ { 'region:'1', 'service_type':'x', 'url':'http://y' },
             { 'region:'2', 'service_type':'x', 'url':'http://y' }]

         then only one entry will be returned since they share a common URL:
           [ { 'region:'1', 'service_type':'x', 'url':'http://y' }]

        """
        auth_ref = get_appropriate_auth_ref(self.token)
        urls = auth_ref.service_catalog.get_endpoints(
            service_type=service_type,
            endpoint_type=endpoint_type,
            region_name=region)

        if not urls or not urls[service_type]:
            return []

        # Return only one endpoint per unique URL
        return {u['url']: u for u in urls[service_type]}.values()

    @static.cache_on_arguments()
    def get_service_endpoint(self, service_type,
                             endpoint_type=get_conf("services.endpoint_type",
                                                    default="internalURL"),
                             region=None):
        """
        Get the internal service endpoint for the given service type.  In a
        multi-region environment where no region is passed, only a single
        endpoint will be returned.
        """
        auth_ref = get_appropriate_auth_ref(self.token)
        try:
            return auth_ref.service_catalog.url_for(
                service_type=service_type,
                endpoint_type=endpoint_type,
                region_name=region)
        except exceptions.EndpointNotFound:
            pass

    def get_session(self):
        """
        Get a project-scoped session.
        """
        return _get_session(self.token)

    def get_domain_session(self):
        """
        Get a domain-scoped session.  It is expected that this will only be
        used by plugins that need to manipulate keystone users.
        """
        return _get_domain_session(self.token)

    @static.cache_on_arguments()
    def get_regions(self):
        """
        Obtain a list of regions available in the current environment.
        """
        client = ksclient3.Client(session=self.get_session(),
                                  endpoint_type=get_conf(
                                      "services.endpoint_type",
                                      default="internalURL"),
                                  user_agent=USER_AGENT)

        return client.regions.list()
