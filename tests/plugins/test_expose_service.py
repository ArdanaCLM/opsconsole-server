# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

from bll.plugins.service import SvcBase
from tests.util import TestCase
from bll.api.request import BllRequest
from bll.common.job_status import get_job_status
from bll import api
from tests import util
import time
import logging


class TestExposeSvc(TestCase):

    def testNull(self):

        request = {
            api.TARGET: 'general',
            api.DATA: {
                api.OPERATION: 'null'
            }
        }

        reply = SvcBase.spawn_service(BllRequest(request))
        self.assertEqual(reply[api.STATUS], api.COMPLETE)

    def testOp(self):

        request = {
            api.TARGET: 'expose',
            api.DATA: {
                api.OPERATION: 'valid_op'
            }
        }

        reply = SvcBase.spawn_service(BllRequest(request))
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
        self.assertEqual(reply[api.DATA], 'ok')

    def testOpGet(self):

        request = {
            api.TARGET: 'expose',
            api.ACTION: 'GET',
            api.DATA: {
                api.OPERATION: 'valid_op'
            }
        }

        reply = SvcBase.spawn_service(BllRequest(request))
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
        self.assertEqual(reply[api.DATA], 'ok')

    def testOpPost(self):

        request = {
            api.TARGET: 'expose',
            api.ACTION: 'POST',
            api.DATA: {
                api.OPERATION: 'valid_op'
            }
        }

        reply = SvcBase.spawn_service(BllRequest(request))
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
        self.assertEqual(reply[api.DATA], 'ok')

    def testAction(self):

        request = {
            api.TARGET: 'expose',
            api.ACTION: 'act',
        }

        reply = SvcBase.spawn_service(BllRequest(request))
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
        self.assertEqual(reply[api.DATA], 'action')

    def testInvalidOp(self):

        request = {
            api.TARGET: 'expose',
            api.DATA: {
                api.OPERATION: 'not_exposed'
            }
        }

        # Suppress exception log
        with util.log_level(logging.CRITICAL, 'bll'):
            reply = SvcBase.spawn_service(BllRequest(request))
        self.assertEqual(reply[api.STATUS], api.STATUS_ERROR)
        self.assertIn('Unsupported', reply[api.DATA][0][api.DATA])

    def testMissingOp(self):

        request = {
            api.TARGET: 'expose',
            api.DATA: {
                api.OPERATION: 'foo'
            }
        }

        # Suppress exception log
        with util.log_level(logging.CRITICAL, 'bll'):
            reply = SvcBase.spawn_service(BllRequest(request))
        self.assertEqual(reply[api.STATUS], api.STATUS_ERROR)
        self.assertIn('Unsupported', reply[api.DATA][0][api.DATA])

    def testSlowOp(self):

        request = {
            api.TARGET: 'expose',
            api.DATA: {
                api.OPERATION: 'slow_op'
            }
        }

        # Suppress exception log
        txn_id = None
        with util.log_level(logging.CRITICAL, 'bll'):
            reply = SvcBase.spawn_service(BllRequest(request))
            txn_id = reply.get(api.TXN_ID)
        self.assertEqual(reply[api.PROGRESS]['percentComplete'], 0)
        self.assertEqual(api.STATUS_INPROGRESS, reply[api.STATUS])

        time.sleep(0.1)
        reply = get_job_status(txn_id)
        self.assertEqual(reply[api.PROGRESS]['percentComplete'], 100)

    def testMultiDecorator(self):

        request = {
            api.TARGET: 'expose',
            api.DATA: {
                api.OPERATION: 'op1'
            }
        }

        reply = SvcBase.spawn_service(BllRequest(request))
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
        self.assertEqual(reply[api.DATA], 'multi')

        request[api.DATA][api.OPERATION] = 'op2'
        reply = SvcBase.spawn_service(BllRequest(request))
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
        self.assertEqual(reply[api.DATA], 'multi')

    def test_spawn_long(self):
        """
        This function is nearly identical to test_spawn_long in
        test_service_collection.py, with the only difference being the
        target and operation in the request.  This illustrates that the
        behavior of the new @expose method is the same as the old
        handle/complete for asynchronous calls.
        """

        pauses = 5
        pause_sec = 0.1

        bll_request = {
            api.TARGET: 'expose',
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

    def test_returned_data(self):
        request = {
            api.TARGET: 'expose',
            api.DATA: {
                api.OPERATION: 'data_in_response'
            }
        }

        reply = SvcBase.spawn_service(BllRequest(request))
        # even though the data_in_response method doesn't return anything,
        # we should still see data
        self.assertEqual(reply[api.DATA], 'blah')
