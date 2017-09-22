# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
import operator
from bll.common.util import scrub_passwords, new_txn_id

from bll.common.exception import InvalidBllRequestException
from bll import api


class BllRequest(dict):

    RESERVED = (api.TARGET, api.ACTION, api.TXN_ID, api.REGION, api.AUTH_TOKEN,
                api.DATA, api.LANGUAGE)

    def __init__(self, request=None, target=None, auth_token=None,
                 operation=None, action=None, data=None, txn_id=None,
                 region=None, language=None, **kwargs):
        """
        Create the BLL request.  Requests are generally created in one of two
        ways:
        1. With only a request parameter - These include calls from the
           external REST API (where request is populated with the JSON payload)
           and from older tests and cross-plugin calls
        2. Explicit parameters and no request parameter - These are mostly from
           tests and plugins

        BllRequest is just a slightly enhanced dictionary.  Historically the
        information specific to a particular request has been passed as a
        nested dictionary whose key is 'data'.  While this avoids potential
        conflicts between RESERVED key names and those needed by the given
        operation, in practice this has never been an issue.  The down side is
        that the request JSON has unnecessary nesting, which makes reading
        requests more confusing and requires extra code to navigate down into
        the nested dictionary.

        To make matters worse, a convention has arisen in a few services to
        expect their data in another dictionary nested within the 'data'
        dictionary, whose key name is 'data' or 'request_data'. Therefore these
        APIs have doubly nested dictionary. This is just crazy and must be
        fixed.

        Going forward, callers should place all parameters at the top level of
        the request rather than embedding them in a nested dictionary.

        In order to provide backward compatibility for older UI calls (which
        still populates the 'data' dictionary) and older BLL plugins (which
        still expect 'data' to be populated), this constructor will yield a
        request object where all non-RESERVED request fields will be populated
        as both top-level elements and as elements in the data dictionary.
        """

        if request:
            # When called via the external API, request will be dictionary
            # populated with a dictionary populated from the JSON payload.
            super(BllRequest, self).__init__(request)

        if kwargs:
            self.update(**kwargs)

        if not self.get(api.DATA):
            self[api.DATA] = {}

        if target:
            self[api.TARGET] = target

        if isinstance(data, dict):
            self[api.DATA].update(data)

        # Copy the operation into the data dict.  The operation
        # may either be in a specific argument (when called from other plugins)
        # or already populated in (when called from external REST
        # API)
        op = operation or self.get(api.OPERATION)
        if op:
            self[api.DATA][api.OPERATION] = op

        # Provide backward compatibility to older callers by copying
        # everything from the data dictionary into top-level elements of the
        # request.

        for key, value in self[api.DATA].iteritems():
            if key not in self.RESERVED:
                self[key] = value

        # Provide backward compatibility to older services by copying
        # everything from top level of the request into the data
        # dictionary
        for key, value in self.iteritems():
            if key not in self.RESERVED and key not in self[api.DATA]:
                self[api.DATA][key] = value

        if action:
            self[api.ACTION] = action

        if auth_token:
            self[api.AUTH_TOKEN] = auth_token

        if txn_id:
            self[api.TXN_ID] = txn_id

        if region:
            self[api.REGION] = region

        if language:
            self[api.LANGUAGE] = language

        self._verify_request()

        if not self.get(api.TXN_ID):
            self[api.TXN_ID] = new_txn_id()

        self.txn_id = self[api.TXN_ID]

    def _verify_request(self):
        if len(self) == 0:
            raise InvalidBllRequestException('No request')

        # txn_id is required when requesting a job status update
        if self.is_job_status_request() and not self.get(api.TXN_ID):
            raise InvalidBllRequestException('No txn_id')

    def is_service_request(self):
        return not self.is_job_status_request()

    def is_job_status_request(self):
        return self.get(api.JOB_STATUS_REQUEST, False)

    def get_data(self):
        """
        return a dictionary of all items from data except 'operation',
        'version', and any RESERVED words
        """
        excluded = self.RESERVED + (api.OPERATION, api.VERSION)
        return {k: v for k, v in self.iteritems() if k not in excluded}

    def __str__(self):

        # Print the DATA portion of the request with the OPERATION first,
        # and other keys afterward in sorted order
        data = self.get(api.DATA)
        data_list = []

        text = ""
        if api.TARGET in self:
            text += "TARGET:%s " % self[api.TARGET]

        if self.is_job_status_request():
            text += "STATUS_REQUEST "

        if api.ACTION in self:
            text += "ACTION:%s " % self[api.ACTION]

        if isinstance(data, dict):
            sorted_keys = sorted(data, key=operator.itemgetter(1))

            if api.OPERATION in sorted_keys:
                sorted_keys.remove(api.OPERATION)
                text += "OPERATION:%s " % data[api.OPERATION]

            for key in sorted_keys:
                value = data[key]
                data_list.append("%s:%s" % (key, scrub_passwords(value)))

            text += scrub_passwords("DATA:{%s} " % ",".join(data_list))

        if api.TXN_ID in self:
            text += "TXN:%s " % self[api.TXN_ID]

        return text
