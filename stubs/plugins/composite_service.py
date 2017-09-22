# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

from bll.plugins import service
from bll import api
from bll.api.request import BllRequest


class CompositeSvc(service.SvcBase):
    """
    Service with sync calls that calls sync calls in other plugins
    """

    @service.expose()
    def composite(self):
        foo = self.call_service(target='general', operation='echo', data={
            'message': 'foo'})
        bar = self.call_service(target='general', operation='echo', data={
            'message': 'bar'})
        return [foo, bar]

    @service.expose()
    def fail(self):
        return self.call_service(target='general', operation='failhandle')


class CompositeAsyncSvc(service.SvcBase):
    def handle(self):

        self.response[api.STATUS] = api.STATUS_INPROGRESS
        self.response[api.PROGRESS] = {api.PERCENT_COMPLETE: 0}
        return self.response

    def complete(self):
        """
        Async call that calls async calls in other plugins
        """
        if self.operation == 'progress':
            request = BllRequest(target="general", operation='progress',
                                 data={'num_pauses': 2})
        elif self.operation == 'fail':
            request = BllRequest(target="general", operation="failcomplete")

        self.response[api.DATA] = self.call_service_async(request,
                                                          polling_interval=0.1)

        self.response[api.PERCENT_COMPLETE] = dict(percentComplete=100)
        self.response.complete()
        return self.response


class CompositeAsyncExposeSvc(service.SvcBase):
    """
    Async call that calls async calls in other plugins, all using @expose
    """
    @service.expose(is_long=True)
    def go(self, validate):
        if validate:
            return

        if self.operation == 'progress':
            request = BllRequest(target="general", operation='progress',
                                 data={'num_pauses': 2})
        elif self.operation == 'fail':
            request = BllRequest(target="general", operation="failcomplete")

        return self.call_service_async(request, polling_interval=0.1)
