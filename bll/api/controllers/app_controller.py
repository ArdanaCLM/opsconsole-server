#
# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
#
import logging
import json

from pecan import response, request, expose
from pecan.rest import RestController
from bll.api.request import BllRequest
from bll import api
from bll.common.util import context, scrub_passwords, response_to_string
from bll.common.job_status import get_job_status
from bll.plugins.service import SvcBase

LOG = logging.getLogger(__name__)

region = None


class AppController(RestController):

    @expose('json')
    def post(self, **kwargs):

        # generate a uniq id solely for the purpose of more
        # easily matching up request/responses in the log

        try:
            bll_request = BllRequest(json.loads(request.body))

            # Add to thread local storage for logging
            context.txn_id = bll_request.txn_id

            if 'X-Auth-Token' in request.headers:
                bll_request[api.AUTH_TOKEN] = request.headers['X-Auth-Token']

            bll_request[api.LANGUAGE] = self.get_language(
                request.headers.get('Accept-Language'))

            LOG.info("Received %s", bll_request)

            # initial service request?
            if bll_request.is_service_request():
                ret = SvcBase.spawn_service(bll_request)

            else:
                # Poll to retrieve async response
                ret = get_job_status(bll_request.txn_id)

            response.status = 201

            if isinstance(ret, dict):
                logstr = response_to_string(ret)
                LOG.info("Response %s", logstr)

        except ValueError as info:
            # json.loads was unable to convert the request to json
            LOG.error("Error converting request body to json: %s. "
                      "Request body: %s",
                      info, request.body)
            response.status = 400
            ret = {
                api.STATUS: api.STATUS_ERROR,
                api.DATA: [{api.DATA: str(info)}]
            }
            LOG.info("Response ValueError: %s", scrub_passwords(ret))

        except Exception as info:
            response.status = 400
            ret = {
                api.STATUS: api.STATUS_ERROR,
                api.DATA: [{api.DATA: str(info)}]
                }
            LOG.info("Response Exception: %s", scrub_passwords(ret))

        # Clear out txn_id as it leaves the system
        context.txn_id = ''
        return ret

    def get_language(self, accept_language):

        # Obtains the set of languages from the parameter (Accept-Language
        # http header) and returns the best match against those languages
        # that are available.
        #
        # The language parameter is a comma-separated list of languages.  Each
        # language may contain a quality value, which is a string like
        #  ;q=0.5 that is appended to the language name.  For example:
        #     da, en-gb;q=0.8, en;q=0.7

        AVAILABLE_LANGUAGES = ['en', 'ja', 'zh']
        DEFAULT_LANGAUAGE = 'en'

        if accept_language:
            accept_language = accept_language.replace(' ', '')

            # Extract languages and their priorities from the Accept-Language
            # header.  Using the above example string, this logic would
            # populate the languages array with:
            # [ ('da', 1.0), ('en-gb', 0.8), ('en', 0.7) ]
            languages = []
            for language_str in accept_language.split(','):
                parts = language_str.split(';q=')
                language = parts[0]
                if len(parts) > 1:
                    priority = float(parts[1])
                else:
                    priority = 1.0
                languages.append((language, priority))

            # Sort languages according to preference (highest first)
            languages.sort(key=lambda t: t[1], reverse=True)

            # Find first exact match against the available languages.  In
            # the above example, if en-gb was in Accept-Languages, a match
            # against an available language of 'en-GB' should be preferred
            # above a match against the generic 'en'.  In other words, if
            # the user wants British english and it is available, it should
            # be used instead of the generic (likely US) English translation.
            for want, priority in languages:
                for avail in AVAILABLE_LANGUAGES:
                    if want.replace('-', '_').lower() == avail.lower():
                        return avail

            # Fall back to find first language match (prefix e.g. 'en' for
            # 'en-GB')
            for want, priority in languages:
                for avail in AVAILABLE_LANGUAGES:
                    if want.split('-')[0].lower() == avail.lower():
                        return avail

        return DEFAULT_LANGAUAGE
