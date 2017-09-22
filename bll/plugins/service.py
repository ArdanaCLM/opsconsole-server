# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

import logging
import inspect
import pykka
import copy
import time
import traceback
from bll.common import util

from bll.common.exception import InvalidBllRequestException, BllException
from bll.api.auth_token import TokenHelpers
from bll.api.response import BllResponse
from bll.api.request import BllRequest
from bll import api
from bll.common.job_status import get_job_status, update_job_status
from bll.common import i18n
from bll.common.util import context, new_txn_id
from stevedore import driver
from requests.exceptions import HTTPError

LOG = logging.getLogger(__name__)


def expose(operation=None, action='GET', is_long=False):
    """ A decorator for exposing methods as BLL operations/actions

    Keyword arguments:

    * operation
        the name of the operation that the caller should supply in
        the BLL request.  If this optional argument is not supplied,
        then the operation name will be the name of the method being
        decorated.

    * action
        the name of the action (typically ``GET``, ``PUT``, ``DELETE`` or
        ``POST``) that will be matched against the BLL request.  If this
        optional argument is not supplied, then the dispatching
        mechanism will ignore the action.

    * is_long
        indicates that the method being decorated is a long-running
        function.  Long-running methods may either be called once
        (via complete) or twice (via handle for validation and via
        for the rest) depending on their signature -- if the
        method has an argument (other than self), then it will be
        called twice, in which case the parameter will be populated
        with a boolean indicating whether it is being called via
        handle; in this case, the function should return a recommended
        polling interval.

    Note, if you override handle or complete, this decorations will be ignored!

    When a normal (short-running) method is called, its return value should
    just be the data portion of the response. The handle method will take
    care of building a full BllResponse structure and placing this return
    value in the data portion.   Otherwise, if there are any problems, the
    method should just throw an appropriate exception.  The handle method
    will catch the exception and package it up in an appropriate BllResponse
    object.

    The decorator can be applied multiple times to the same function, in
    order to permit a function to be called via multiple operations.  For
    example::

        class MySvc(SvcBase)
            @expose('add_stuff')
            @expose('update_stuff')
            def add_or_update(self):
                ...

    """

    def decorate(f):
        f.exposed = True
        if not hasattr(f, 'operation'):
            f.operation = []

        f.operation.append(operation or f.__name__)

        if action:
            f.action = action

        if is_long:
            f.is_long = is_long

        # normally a decorator returns a wrapped function, but here
        # we return f unmodified, after registering it
        return f

    return decorate


class SvcBase(pykka.ThreadingActor):
    """
    Base class for plugins.
    """
    def __init__(self, bll_request=None):
        super(SvcBase, self).__init__()

        # Extract common fields into attributes
        if not isinstance(bll_request, BllRequest):
            raise InvalidBllRequestException('Invalid request class')
        self.request = bll_request
        self.response = BllResponse(self.request)
        if api.AUTH_TOKEN in self.request:
            self.token_helper = TokenHelpers(self.request.get(api.AUTH_TOKEN))
            self.token = self.request.get(api.AUTH_TOKEN)

        request_data = self.request.get(api.DATA, {})
        self.action = self.request.get(api.ACTION)

        self.api_version = None
        self.operation = None
        self.data = {}
        self.txn_id = self.request.txn_id
        self.region = self.request.get(api.REGION)

        # Assign _ as a member variable in this plugin class for localizing
        # messages
        self._ = i18n.get_(self.request.get(api.LANGUAGE, 'en'))

        # Extract request data, filtering out known keys
        for k, v in request_data.iteritems():
            if k == api.OPERATION:
                self.operation = v
            elif k == 'suggest_sync':
                # Omit the obsolete, poorly-supported suggest_sync flag
                pass
            elif k == api.VERSION:
                self.api_version = v
            else:
                self.data[k] = v

    @staticmethod
    def spawn_service(bll_request):
        """
        Call the targeted service, using stevedore to load the plugin whose
        name matches the 'target' field of the incoming request.
        """
        srv = None
        # Assign _ in this function for localizing messages
        _ = i18n.get_(bll_request.get(api.LANGUAGE, 'en'))
        try:
            mgr = driver.DriverManager(
                namespace='bll.plugins',
                name=bll_request.get(api.TARGET))

            srv = mgr.driver.start(bll_request=bll_request).proxy()
            reply = srv.sc_handle()
            result = reply.get()
            srv.sc_complete()
            return result

        except Exception as e:
            LOG.exception('spawn_service failed')
            if srv is not None:
                srv.stop()

            response = BllResponse(bll_request)

            if isinstance(e, HTTPError):
                message = e.message
            elif isinstance(e, BllException):
                # Localize the overview field from the BllException
                prefix = _(e.overview)
                message = _("{0}: {1}").format(prefix, e)
            else:
                message = "%s" % e

            response.error(message.rstrip())

            return response

    def handle(self):
        """
        Handle the request by dispatching the request to the appropriate
        method.  Override this method if desired, to implement your own
        dispatching and execution of short-running work.
        """
        if not self.operation and not self.action:
            raise InvalidBllRequestException(self._(
                "Operation and action missing"))

        method = self._get_method(self.operation, self.action)
        if method is None:
            raise InvalidBllRequestException(
                self._("Unsupported operation: {}").format(self.operation))

        if getattr(method, 'is_long', False):
            self.response[api.PROGRESS] = dict(percentComplete=0)
            self.response[api.STATUS] = api.STATUS_INPROGRESS
            polling_interval = 10

            if method.im_func.func_code.co_argcount > 1:
                # If the long-running method expects an argument, call it
                # set to True and expect a polling interval in return
                polling_interval = method(True) or polling_interval

            self.response[api.POLLING_INTERVAL] = \
                getattr(self, api.POLLING_INTERVAL, 10)

            self.update_job_status(percentage_complete=0)
            return self.response

        data = method()

        # In cases where we don't have the data in the response, it
        # had better be in the return value.
        #    i.e. compute_summary_service: resource_history()
        if not self.response[api.DATA]:
            self.response[api.DATA] = data

        self.response[api.PROGRESS] = dict(percentComplete=100)
        self.response.complete()
        return self.response

    def complete(self):
        """
        Complete the request. Override this method and do long running
        processing here.
        """
        if not self.operation and not self.action:
            return

        method = self._get_method(self.operation, self.action)
        if method is None:
            return

        if getattr(method, 'is_long', False):

            try:
                if method.im_func.func_code.co_argcount > 1:
                    # If the long-running method expects an argument, call it
                    # set to False to indicate that it is being called
                    # during complete
                    response = method(False)
                else:
                    response = method()

                # Permit the calling function to just return a normal
                # value, and then just add it to the 'data' element of the
                # existing self.response
                if isinstance(response, BllResponse):
                    self.response = response
                else:
                    self.response[api.DATA] = response

                self.response[api.PROGRESS] = dict(percentComplete=100)
                self.response.complete()

            except Exception as e:
                self.response.error("%s" % e)

            return self.response

    def _get_method(self, operation=None, action=None):
        """
        Use inspection to get the name of the @exposed function that
        corresponds to the operation and action being requested

        If there is only one method whose exposed name matches the operation,
        then that method is returned, regardless of the action.  If there is
        more, then the action will be consulted to decide which to return.
        """

        candidates = []

        # Find all candidates -- those members whose name matches the
        #   operation, ignoring the action.
        for name, f in inspect.getmembers(self, inspect.ismethod):
            # Only look at those that are exposed
            if not getattr(f, 'exposed', False):
                continue

            # If operation is specified, the function must expose that op
            op_list = getattr(f, 'operation', [])
            if operation and operation not in op_list:
                continue

            candidates.append((name, f))

        if not candidates:
            return

        # In most cases, there is only a single function with the given
        # operation, so we will return that.
        if len(candidates) == 1:
            name, f = candidates[0]
            return f

        # If action is specified, the function must expose that action
        for name, f in candidates:
            if action == getattr(f, 'action', None):
                return f

    def sc_handle(self):
        """
        Handle the request. Called by the SvcCollection class. Do not override,
        this method. Override method handle.
        """

        context.txn_id = self.request.txn_id
        reply = self.handle()
        return copy.deepcopy(reply)

    def sc_complete(self):
        """
        complete the request. Called by the SvcCollection class. Do not
        override this method. Override method 'complete'.
        """
        try:
            bll_response = self.complete()
            if bll_response is not None:
                self.put_resource(self.request.txn_id, bll_response)
        except Exception as e:
            LOG.exception('sc_complete failed.')
            self.response.exception(traceback.format_exc())
            self.put_resource(self.request.txn_id, self.response.error(
                "%s" % e))
        finally:
            self.stop()

    def update_job_status(self, msg=None, percentage_complete=0,
                          txn_id=None, **kwargs):

        if percentage_complete is not None:
            self.response[api.PROGRESS] = {api.PERCENT_COMPLETE:
                                           percentage_complete}

        if msg:
            self.response[api.DATA] = msg

        self.response.update(**kwargs)

        txn = txn_id or self.txn_id
        update_job_status(txn, self.response)

    def put_resource(self, txn_id, msg):
        update_job_status(txn_id, msg)

    @classmethod
    def is_available(cls, available_services):
        """
        Returns a boolean to indicate whether this plugin is available, i.e.,
        that all of the dependent services and requirements that this plugin
        needs are available.  The function is supplied a lists of openstack
        services from keystone that are available.

        This check will not be called each time the plugin is executed, so it
        can afford to be somewhat slow.  It is expected to only be called when
        the client (UI) requests a list of available plugins.
        """
        needs = cls.needs_services()
        for service in needs:
            if service not in available_services:
                return False

        return True

    @classmethod
    def needs_services(cls):
        """
        List of services that this plugin uses, if any.  When populated by
        the plugin, the default implementation of is_available (above) can
        easily check whether all needed services are available by consulting
        this function.

        Note that it is generally unnecessary to indicate that keystone is
        required for a given plugin since keystone already has to be running
        for the operations console to even let a user login.
        """
        return []

    def call_service_async(self,
                           request=None,
                           target=None,
                           auth_token=None,
                           operation=None,
                           action=None,
                           data=None,
                           region=None,
                           polling_interval=None,
                           max_polls=0,
                           offset=0,
                           scale=1.0,
                           **kwargs):
        """
        Call an asynchronous service in another plugin, and wait for it
        to complete before returning. If a request is supplied, its values
        will be used as the basis of the call, and any other parameters will
        override the values in the request.  If a request is not supplied, a
        new BllRequest will be constructed from the other parameters.

        This function shields the caller from the complexities of the
        standard reply mechanism (which returns a dictionary with status values
        and deeply embedded return data), and offers a more pythonic interface
        where the data is returned directly from the function, and exceptions
        are thrown in the event of errors.

        This function should only be called from within an asynchronous
        service; calling an asynchronous service from a synchronous service
        would probably cause the calling operation to time out.

        The asynchronous service being called may return a percent complete
        value.  If so, then update_job_status will be called to update the
        percentage complete of the calling service.  The percentage value of
        the called function will be scaled and offset added so that callers
        which perform multiple steps will have their percentages updated
        correctly.

        :param request: Request dictionary or BllRequest (optional)
        :param target: Target service to invoke (optional)
        :param token: Authorization token to use (optional).  If neither token
                      nor request is specified, then the token from the current
                      service will be used.
        :param operation: Operation in the service to call (optional)
        :param action: Action in the service to use (optional)
        :param data: Data object to place into the request (optional)
        :param region: Restrict operation to the given region (optional)
        :param polling_interval: Timeout, in seconds, to wait between polls
                                 for status from the async request (optional)
        :param max_polls: Limit of the number of polls to be attempted.
                          If 0 or not specified, then attempts will be
                          unlimited.
        :param offset: Value added to percentComplete of target function
                          when updating status of calling plugin (optional)
        :param scale:  Value multiplied by percentComplete of target function
                          when updating status of calling plugin (optional)
        :param \*\*kwargs: Additional items to pass to the BllRequest
                         constructor (optional)
        :return: The results of the :func:`handle` method of the
                 called service
        """

        if polling_interval is None:
            try:
                polling_interval = request[api.POLLING_INTERVAL]
            except (AttributeError, TypeError, KeyError):
                polling_interval = 10

        request = self._build_request(request, target, auth_token, operation,
                                      action, data, region, **kwargs)

        handle_reply = SvcBase.spawn_service(request)
        txn_id = handle_reply.get(api.TXN_ID)

        pct_key = ".".join((api.PROGRESS, api.PERCENT_COMPLETE))

        poll = 0
        reply = get_job_status(txn_id)
        while reply.get(api.STATUS) in (api.STATUS_INPROGRESS,
                                        api.STATUS_NOT_FOUND):

            if max_polls > 0 and poll < max_polls:
                raise Exception(self._("Timed out waiting for {}").format(
                                request))

            pct = util.get_val(reply, pct_key)
            if pct:
                overall_pct = offset + scale * pct
                self.update_job_status(percentage_complete=overall_pct)

            time.sleep(polling_interval)
            reply = get_job_status(txn_id)
            poll += 1

        data = reply.get(api.DATA)
        if reply.get(api.STATUS) == api.STATUS_ERROR:
            # extract the error message and throw it
            try:
                message = data[0][api.DATA]
            except (TypeError, IndexError, KeyError):
                message = data or self._("Failure calling {} service").format(
                    target)

            raise Exception(message)

        pct = util.get_val(reply, pct_key)
        if pct:
            overall_pct = offset + scale * pct
            self.update_job_status(percentage_complete=overall_pct)

        return data

    def call_service(self,
                     request=None,
                     target=None,
                     auth_token=None,
                     operation=None,
                     action=None,
                     data=None,
                     region=None,
                     **kwargs):
        """
        Call a synchronous service in another plugin, i.e. just the
        handle method.  If a request is supplied, its values will be used
        as the basis of the call, and any other parameters will override the
        values in the request.  If a request is not supplied, a new BllRequest
        will be constructed from the other parameters.

        :param request: Request dictionary or BllRequest (optional)
        :param target: Target service to invoke (optional)
        :param token: Authorization token to use (optional).  If neither token
                      nor request is specified, then the token from the current
                      service will be used.
        :param operation: Operation in the service to call (optional)
        :param action: Action in the service to use (optional)
        :param data: Data object to place into the request (optional)
        :param region: Restrict operation to the given region (optional)
        :param \*\*kwargs: Additional items to pass to the BllRequest
                         constructor (optional)
        :return: The results of the :func:`handle` method of the
                 called service
        """
        request = self._build_request(request, target, auth_token, operation,
                                      action, data, region, **kwargs)

        response = SvcBase.spawn_service(request)
        if response[api.STATUS] == api.COMPLETE:
            return response[api.DATA]

        try:
            message = response[api.DATA][0][api.DATA]
        except KeyError:
            message = response.get(api.DATA)

        raise Exception(message)

    def _build_request(self, request=None, target=None, auth_token=None,
                       operation=None, action=None, data=None, region=None,
                       **kwargs):

        """
        Construct a request object using the following, in priority order (
        highest priority first):
        1. Function arguments (e.g. operation)
        2. Values in the ``request`` argument
        3. Values from the service making the request for fields that are
           commonly inherited (txn, region, auth_token)

        For example, if the auth_token is passed as a parameter, it will be
        used; otherwise, the auth_token will be taken from any request
        object passes as a parameter; otherwise it will be copied from the
        calling service.
        """
        txn_id = new_txn_id(self.txn_id)
        language = self.request.get(api.LANGUAGE)

        if not region:
            if request:
                region = request.get(api.REGION)

            region = region or self.region

        req = BllRequest(request=request, target=target,
                         auth_token=auth_token, operation=operation,
                         action=action, data=data, txn_id=txn_id,
                         region=region, language=language, **kwargs)

        if not req.get(api.AUTH_TOKEN) and getattr(self, 'token_helper', None):
            req[api.AUTH_TOKEN] = self.token_helper.get_user_token()

        return req
