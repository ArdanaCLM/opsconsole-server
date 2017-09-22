# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

import json
import logging

from pecan import expose, request
from pecan.core import Response
from pecan.secure import unlocked, SecureController

from bll.api.auth_token import login, validate
from bll.api.controllers.app_controller import AppController

LOG = logging.getLogger(__name__)


class V1(SecureController):

    _custom_actions = {
        'auth_token': ['POST']
        }

    def __init__(self, *args, **kwargs):
        super(V1, self).__init__(*args, **kwargs)

    @classmethod
    def check_permissions(self):
        """
        Since this object extends SecureController, this function will
        automatically be called on all exposed rest calls, except for those
        decorated as @unlocked or decorated with a custom @secure function
        """
        req_body = None
        try:
            req_body = json.loads(request.body)
            # Bypass deploy permission checks
            if req_body['target'] == 'eula':
                LOG.debug("v1 bypass check_permissions for %s",
                          req_body['target'])
                return True
        except Exception:
            pass

        if 'X-Auth-Token' not in request.headers:
            return False

        token = request.headers['X-Auth-Token']

        # For backward compatibility with old HDP installers that use the
        # old token blob, extract the token from the blob
        if isinstance(req_body, dict) and req_body.get('target') == 'plugins'\
                and "management_appliance" in token:
            try:
                blob = json.loads(token)
                ma_tokens = blob['management_appliance']['tokens']
                token = ma_tokens[0]['auth_token']
                request.headers['X-Auth-Token'] = token

            except Exception:
                pass

        return validate(token)

    @unlocked
    @expose(content_type='application/json')
    def auth_token(self, username=None, password=None, tenant=None):
        """
        POST /auth_token
        BODY {"username": username, "password": password}
        """
        body = json.loads(request.body)
        username = body['username']
        password = body['password']

        LOG.debug("/auth_token user=%s" % (username))

        auth_ref = None
        try:
            auth_ref = login(username, password)

            return json.dumps({
                'token': auth_ref.auth_token,
                'expires': auth_ref.expires.isoformat()
            })

        except Exception as e:
            LOG.info("User login as %s failed: %s" % (username, str(e)))
            return Response(str(e), 401)

    @unlocked
    # Return a result when querying the root document.
    @expose(generic=True, template=None, content_type='text/html')
    @expose(generic=True, template=None, content_type='application/json')
    def index(self):
        return '"Operations Console API v1"'

    # V1 App Controller
    bll = AppController()
