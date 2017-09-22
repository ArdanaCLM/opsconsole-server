# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

import logging
from pecan.hooks import PecanHook

LOG = logging.getLogger(__name__)


class RestHook(PecanHook):
    '''
    RestHook is class used to log info before() and after()
    controller code is run. If an exception is raised in
    the controller then this is handled by on_error().
    '''

    def before(self, state):
        '''
        Using 'before' hook to inspect state before controller code is run.
        '''
        LOG.info('Request from: %s "%s %s"' %
                 (state.request.remote_addr, state.request.method,
                  state.request.path_qs))

    def after(self, state):
        '''
        Using 'after' hook to inspect state after controller code is run.
        '''
        LOG.info('Response  to: %s "%s %s" %s %s' %
                 (state.request.remote_addr, state.request.method,
                  state.request.path_qs, state.response.status_code,
                  state.response.content_length))

    def on_error(self, state, e):
        '''
        Using 'on_error' hook to inspect state when exception
        raised in controller.
        Will have default status_code of "Bad Request", 400
        '''
        status_code = getattr(e, 'status_code', 400)
        state.response.status = state.response.status_code = status_code
        LOG.warn('Exception %r in: %s "%s %s" %s %s' %
                 (e, state.request.remote_addr, state.request.method,
                  state.request.path_qs, state.response.status_code,
                  state.response.content_length))
        return state.response
