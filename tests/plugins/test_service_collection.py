# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
import mock
import time
from bll.plugins.service import SvcBase, expose
from tests.util import TestCase, randomword
from bll.api.request import BllRequest
from bll.common.job_status import get_job_status
from bll import api


class TestSvcCollection(TestCase):

    def test_spawn_short(self):
        bll_request = {
            api.TARGET: 'general',
            api.DATA: {
                api.OPERATION: 'null'
            }
        }

        reply = SvcBase.spawn_service(BllRequest(bll_request))
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
        self.assertIsNotNone(reply.get(api.TXN_ID))
        self.assertIn(api.DURATION, reply)
        self.assertIn(api.ENDTIME, reply)
        self.assertIn(api.STARTTIME, reply)

    def test_spawn_long(self):

        pauses = 5
        pause_sec = 0.1

        bll_request = {
            api.TARGET: 'general',
            api.DATA: {
                api.OPERATION: 'progress',
                'pause_sec': pause_sec,
                'num_pauses': pauses,
            }
        }

        reply = SvcBase.spawn_service(BllRequest(bll_request))
        txn_id = reply.get(api.TXN_ID)

        # test the incomplete reply
        self.assertIn(api.TXN_ID, reply)
        self.assertIn(api.PROGRESS, reply)
        self.assertIn(api.POLLING_INTERVAL, reply)
        self.assertIn(api.STARTTIME, reply)
        self.assertIn(api.STATUS, reply)
        self.assertEqual(api.STATUS_INPROGRESS, reply[api.STATUS])

        # wait a little extra before the first poll
        time.sleep(0.1 + pause_sec)

        # read the job status update
        reply = get_job_status(txn_id)
        self.assertEqual(reply[api.TXN_ID], txn_id)
        self.assertIn(api.STARTTIME, reply)
        self.assertIn(api.STATUS, reply)
        self.assertEqual(api.STATUS_INPROGRESS, reply[api.STATUS])
        percent = reply[api.PROGRESS][api.PERCENT_COMPLETE]
        self.assertGreater(percent, 0)
        self.assertLess(percent, 100)

        while reply.get(api.STATUS) != api.COMPLETE:
            time.sleep(pause_sec)
            reply = get_job_status(txn_id)

        self.assertEqual(reply[api.TXN_ID], txn_id)
        self.assertIn(api.DURATION, reply)
        self.assertIn(api.ENDTIME, reply)
        self.assertIn(api.STARTTIME, reply)
        self.assertIn(api.STATUS, reply)
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
        self.assertEqual(reply[api.PROGRESS][api.PERCENT_COMPLETE], 100)

    def test_call_service(self):
        # Test an sync service that calls another sync service via
        # SvcBase.call_service, and fails

        bll_request = {
            api.TARGET: 'composite',
            api.DATA: {api.OPERATION: 'composite'}
        }

        # load the composite plugin
        reply = SvcBase.spawn_service(BllRequest(bll_request))

        self.assertIn(api.TXN_ID, reply)
        self.assertIsNotNone(reply.get(api.TXN_ID))
        self.assertIn(api.DURATION, reply)
        self.assertIn(api.ENDTIME, reply)
        self.assertIn(api.STARTTIME, reply)
        self.assertIn(api.STATUS, reply)
        self.assertEqual(api.COMPLETE, reply[api.STATUS])
        self.assertEqual(len(reply[api.DATA]), 2)

    def test_call_service_fail(self):
        # Test an sync service that calls another sync service via
        # SvcBase.call_service, and fails

        bll_request = {
            api.TARGET: 'composite',
            api.DATA: {api.OPERATION: 'fail'}
        }

        # load the composite plugin
        reply = SvcBase.spawn_service(BllRequest(bll_request))

        self.assertEqual(api.STATUS_ERROR, reply[api.STATUS])

    def test_call_service_async_indirect(self):

        # Test an async service that calls another async service via
        # SvcBase.call_service_async

        pauses = 2
        pause_sec = 0.1

        request = BllRequest(target='composite-async',
                             operation='progress',
                             data={
                                 'pause_sec': pause_sec,
                                 'num_pauses': pauses,
                             })

        reply = SvcBase.spawn_service(request)
        txn_id = reply.get(api.TXN_ID)

        while reply.get(api.STATUS) != api.COMPLETE:
            time.sleep(pause_sec)
            reply = get_job_status(txn_id)

        self.assertIn(api.TXN_ID, reply)
        self.assertIsNotNone(reply.get(api.TXN_ID))
        self.assertIn(api.DURATION, reply)
        self.assertIn(api.ENDTIME, reply)
        self.assertIn(api.STARTTIME, reply)
        self.assertIn(api.STATUS, reply)
        self.assertEqual(api.COMPLETE, reply[api.STATUS])

    def test_call_service_async_indirect_fail(self):

        # Test an async service that calls another async service via
        # SvcBase.call_async, and which fails

        pause_sec = 0.1
        request = BllRequest(target='composite-async', operation='fail')

        reply = SvcBase.spawn_service(request)
        txn_id = reply.get(api.TXN_ID)

        while reply.get(api.STATUS) in (api.STATUS_INPROGRESS,
                                        api.STATUS_NOT_FOUND):
            time.sleep(pause_sec)
            reply = get_job_status(txn_id)

        self.assertIn(api.TXN_ID, reply)
        self.assertIsNotNone(reply.get(api.TXN_ID))
        self.assertEqual(api.STATUS_ERROR, reply[api.STATUS])

    def test_call_service_async_error_propagated(self):

        # Verify that an error returned by the called function is propagated
        # as an exception to the caller of call_service_async
        class Foo(SvcBase):
            @expose(is_long=True)
            def bar(self):

                try:
                    self.call_service_async(target="general",
                                            operation="errorcomplete",
                                            polling_interval=0.1)
                    self.response.error("Should have thrown an exception")
                except Exception as e:
                    if str(e).startswith("some error happened"):
                        self.response.complete()
                    else:
                        self.response.error("Wrong type of exception")

        svc = Foo(BllRequest(operation="bar"))
        reply = svc.complete()
        self.assertEquals(api.COMPLETE, reply[api.STATUS])

    def test_call_service_async_failure_propagated(self):

        # Verify that an exception returned by the called function is
        # propagated as an exception to the caller of call_service_async
        class Foo(SvcBase):
            @expose(is_long=True)
            def bar(self):

                try:
                    self.call_service_async(target="general",
                                            operation="failcomplete",
                                            polling_interval=0.1)
                    self.response.error("Should have thrown an exception")
                except Exception as e:
                    if str(e).startswith("Intentional"):
                        self.response.complete()
                    else:
                        self.response.error("Wrong type of exception")

        svc = Foo(BllRequest(operation="bar"))
        reply = svc.complete()
        self.assertEquals(api.COMPLETE, reply[api.STATUS])

    def test_call_service_async_return_data(self):

        # Verify that the data returned from the called function is the
        # return value of call_service_async
        class Foo(SvcBase):
            @expose(is_long=True)
            def bar(self):
                msg = randomword()
                reply = self.call_service_async(target="general",
                                                operation="echo_slow",
                                                message=msg,
                                                polling_interval=0.1)
                if reply != msg:
                    self.response.error("Did not receive data")

        svc = Foo(BllRequest(operation="bar"))
        reply = svc.complete()
        self.assertEquals(api.COMPLETE, reply[api.STATUS])

    def test_call_service_async_timeout(self):

        class Foo(SvcBase):
            @expose(is_long=True)
            def bar(self):

                req = BllRequest(target="general",
                                 operation="progress",
                                 pause_sec=0.1,
                                 num_pauses=5)
                try:
                    self.call_service_async(req,
                                            polling_interval=0.1,
                                            max_polls=2)
                    self.response.error("Should have timed out")
                except Exception as e:
                    if str(e).startswith("Timed out"):
                        self.response.complete()
                    else:
                        self.response.error("Wrong type of exception")

        svc = Foo(BllRequest(operation="bar"))
        reply = svc.complete()
        self.assertEquals(api.COMPLETE, reply[api.STATUS])

    def test_call_service_async_with_progress(self):

        class Foo(SvcBase):
            @expose(is_long=True)
            def bar(self):
                req = BllRequest(target="general",
                                 operation="progress",
                                 pause_sec=.1,
                                 num_pauses=5)

                self.call_service_async(req,
                                        polling_interval=0.05,
                                        offset=50,
                                        scale=0.5)
                self.response.complete()
                return self.response

        svc = Foo(BllRequest(operation="bar"))
        svc.update_job_status = mock.Mock()
        reply = svc.complete()
        self.assertEquals(api.COMPLETE, reply[api.STATUS])
        # Note that any_order permits extra calls to have been made, which
        # will happen since there may be multiple calls in a row with the
        # same percentage_complete
        svc.update_job_status.assert_has_calls([
            mock.call(percentage_complete=60.0),
            mock.call(percentage_complete=70.0),
            mock.call(percentage_complete=80.0),
            mock.call(percentage_complete=90.0),
            mock.call(percentage_complete=100.0)], any_order=True)
