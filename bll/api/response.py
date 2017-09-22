# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
#
#     Created on Dec 16, 2014
import time
from bll import api
from bll.common.util import response_to_string


class BllResponse(dict):
    '''
    classdocs
    '''

    def __init__(self, bll_request):
        super(BllResponse, self).__init__()
        '''
        Constructor
        '''
        self[api.STARTTIME] = time.time()
        self[api.TXN_ID] = bll_request[api.TXN_ID]
        self[api.DATA] = []

        # short cuts
        self.txn_id = self.get(api.TXN_ID)

    def complete(self, state=None):
        self[api.ENDTIME] = time.time()
        self[api.DURATION] = self[api.ENDTIME] - self[api.STARTTIME]

        current_state = self.get(api.STATUS)
        if state:
            # If a state is supplied use it
            self[api.STATUS] = state
        elif current_state is None or current_state == api.STATUS_INPROGRESS:
            self[api.STATUS] = api.COMPLETE

        # Otherwise leave self[api.STATUS] unchanged

    def error(self, cause):
        self[api.DATA] = []    # make sure data is a list before appending
        self[api.STATUS] = api.STATUS_ERROR
        self[api.DATA].append({api.DATA: cause})
        return self

    def exception(self, stack_trace):
        self[api.DATA] = []    # make sure data is a list before appending
        self[api.STATUS] = api.STATUS_ERROR
        self[api.DATA].append({'stack_trace': stack_trace})
        return self

    def __str__(self):
        return response_to_string(self)
