# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from builtins import range
from bll import api
from bll.plugins import service
from bll.common import util
import time


class GeneralSvc(service.SvcBase):
    """
    General-purpose service class for testing.
    """

    @service.expose()
    def null(self):
        return []

    @service.expose()
    def echo(self):
        return self.data.get('message')

    @service.expose(is_long=True)
    def echo_slow(self):
        return self.data.get('message')

    @service.expose()
    def failhandle(self):
        raise Exception('Intentional exception in handle')

    @service.expose(is_long=True)
    def failcomplete(self):
        raise Exception('Intentional exception in complete')

    @service.expose(is_long=True)
    def errorcomplete(self):
        self.response.error('some error happened')
        return self.response

    @service.expose(is_long=True)
    def progress(self, validate):
        # Long running process that sleeps and posts updates
        if validate:
            self.pause_sec = util.get_val(self.request, "data.pause_sec", 0.1)
            self.num_pauses = util.get_val(self.request, "data.num_pauses",
                                           100)
            return self.pause_sec
        else:
            for count in range(1, self.num_pauses + 1):
                time.sleep(self.pause_sec)
                progress = (100 * count) / self.num_pauses
                self.response[api.PROGRESS] = {api.PERCENT_COMPLETE: progress}
                self.put_resource(self.request.txn_id, self.response)

            self.response.complete()
            return self.response


class UnavailableSvc(service.SvcBase):
    """
    Class for testing the catalog service.
    """

    @classmethod
    def needs_services(cls):
        return ['SomeMissingService']
