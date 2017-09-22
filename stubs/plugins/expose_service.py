# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from builtins import range
import time

from bll.plugins import service
from bll.common.util import get_val
from bll import api


class ExposeSvc(service.SvcBase):
    """
    Stub class that tests the service dispatching
    via the @expose decorator
    """

    @service.expose('valid_op')
    def do_op(self):
        return 'ok'

    def not_exposed(self):
        pass

    @service.expose(action='act')
    def do_action(self):
        return 'action'

    @service.expose('op1')
    @service.expose('op2')
    def do_multi(self):
        return 'multi'

    @service.expose('slow_op', is_long=True)
    def do_slow_op(self):
        """
        This is an example of a long-running operation that expects no
        parameters.  It should be called once: during the complete() function.
        """
        self.response[api.PROGRESS] = {api.PERCENT_COMPLETE: 100}
        self.put_resource(self.request.txn_id, self.response)
        return self.response

    @service.expose('progress', is_long=True)
    def progress(self, validate):
        """
        This is an example of a long-running operation that expects a
        parameter.  It should be called twice: once during the handle()
        function with the parameter set to True, and once during the
        complete() with the parameter set to False.

        Note that this function behaves the same as the ProgressSvc example,
        and the unit test code that calls it is nearly identical, underscoring
        the fact that the resulting behavior is the same as the legacy
        handle/complete.
        """
        if validate:
            # Validate the input parameters and return a suggested
            # poll interval
            self.pause_sec = get_val(self.request, "data.pause_sec", 0.1)
            self.num_pauses = get_val(self.request, "data.num_pauses", 100)
            return self.pause_sec

        else:
            for count in range(1, self.num_pauses + 1):
                time.sleep(self.pause_sec)
                progress = (100 * count) / self.num_pauses
                self.response[api.PROGRESS] = {api.PERCENT_COMPLETE: progress}
                self.put_resource(self.request.txn_id, self.response)

            self.response.complete()
            return self.response

    @service.expose('data_in_response')
    def data_in_response(self):
        self.response[api.DATA] = 'blah'
        self.response.complete()
        # return nothing
