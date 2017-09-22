# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from datetime import datetime
import json
import logging
import mock
import time

from bll import api
from bll.api.controllers import app_controller
from bll.api.controllers.v1 import V1
from bll.common.job_status import get_job_status
from tests.util import TestCase, log_level


@mock.patch.object(app_controller, 'response')
@mock.patch.object(app_controller, 'request')
class Test(TestCase):

    def test_post_no_txn_id(self, _mock_request, _mock_response):
        _mock_request.body = json.dumps({
            api.TARGET: 'general',
            api.DATA: {
                api.OPERATION: 'null',
            }
        })
        reply = app_controller.AppController().post()
        self.assertEqual(reply[api.STATUS], api.COMPLETE)

    def test_status_update_no_txn_id(self, _mock_request, _mock_response):
        _mock_request.body = json.dumps({
            api.TARGET: 'general',
            api.DATA: {
                api.OPERATION: 'null',
            },
            api.JOB_STATUS_REQUEST: True
        })
        with log_level(logging.CRITICAL, 'bll'):
            reply = app_controller.AppController().post()
        self.assertEqual(reply[api.STATUS], api.STATUS_ERROR)
        self.assertIn("No txn_id", reply[api.DATA][0][api.DATA])

        self.assertTrue(_mock_response.status, 400)

    def test_post_request_fail(self, _mock_request, _mock_response):
        _mock_request.body = json.dumps({api.TARGET: 'general',
                                         api.DATA: {api.OPERATION:
                                                    'failhandle'}})
        # Suppress the expected exception message
        with log_level(logging.CRITICAL, 'bll'):
            reply = app_controller.AppController().post()
        self.assertEqual(reply[api.STATUS], api.STATUS_ERROR)
        self.assertTrue(_mock_response.status, 400)

    def test_post_complete_fail(self, _mock_request, _mock_response):
        _mock_request.body = json.dumps({api.TARGET: 'general',
                                         api.DATA: {api.OPERATION:
                                                    'failcomplete'}})

        # Suppress the expected exception message from service
        with log_level(logging.CRITICAL, 'bll.plugins.service'):
            reply = app_controller.AppController().post()

        time.sleep(0.1)
        txn_id = reply.get(api.TXN_ID)
        reply = get_job_status(txn_id)
        self.assertEqual(reply[api.STATUS], 'error')

    def test_post_complete_error(self, _mock_request, _mock_response):
        _mock_request.body = json.dumps({api.TARGET: 'general',
                                         api.DATA: {api.OPERATION:
                                                    'errorcomplete'}})

        # Suppress the expected exception message from service
        with log_level(logging.CRITICAL, 'bll.plugins.service'):
            reply = app_controller.AppController().post()

        time.sleep(0.1)
        txn_id = reply.get(api.TXN_ID)
        reply = get_job_status(txn_id)
        self.assertEqual(reply[api.STATUS], 'error')
        self.assertEqual(reply[api.DATA][0][api.DATA], 'some error happened')


class TestV1(TestCase):

    @classmethod
    def setUpClass(cls):
        super(TestCase, cls).setUpClass()
        cls.load_test_app()

    def testIndex(self):
        assert self.app.get('/').status_int == 200

    def testV1Index(self):
        assert self.app.get('/v1/').status_int == 200

    @mock.patch('bll.api.controllers.v1.login',
                return_value=type('X', (object,),
                                  dict(auth_token='foo',
                                       expires=datetime.utcnow())))
    def testLogin(self, mock_login):
        body = {'username': 'user', 'password': 'pass'}
        response = self.app.post_json('/v1/auth_token', body)
        self.assertEqual(200, response.status_code)

    @mock.patch('bll.api.controllers.v1.login', side_effect=Exception('foo'))
    def testFailLogin(self, _):
        body = {'username': 'user', 'password': 'pass'}
        response = self.app.post_json('/v1/auth_token', body,
                                      expect_errors=True)
        self.assertEqual(401, response.status_code)

    def testBypassPermissions(self):
        # Create a request object for eula, which bypasses permission checks
        request = type('Request', (object,), dict(body='{"target": "eula"}'))

        with mock.patch('bll.api.controllers.v1.request', request):
            self.assertTrue(V1.check_permissions())

    def testPermissionsWithoutToken(self):

        # Create a request object without a token
        request = type('Request', (object,), dict(body='{"target": "foo"}',
                       headers='{}'))

        with mock.patch('bll.api.controllers.v1.request', request):
            self.assertFalse(V1.check_permissions())

    @mock.patch('bll.api.controllers.v1.validate', return_value=True)
    def testPermissionsWithToken(self, _):

        # Create a request object with a token
        request = type('Request', (object,), dict(body='{"target": "foo"}',
                       headers={"X-Auth-Token": "sometoken"}))

        with mock.patch('bll.api.controllers.v1.request', request):
            self.assertTrue(V1.check_permissions())

    @mock.patch('bll.api.controllers.v1.validate', return_value=True)
    def testBackwardCompat(self, _):

        # Create an old token blob as a json string
        headers = """
           {"management_appliance" : {"tokens": [{"auth_token" : "blah" }]}}
        """

        # Create a bogus request object
        request = type('Request', (object,), dict(body='{"target": "plugins"}',
                       headers={"X-Auth-Token": headers}))

        with mock.patch('bll.api.controllers.v1.request', request):
            self.assertTrue(V1.check_permissions())

    @mock.patch('bll.api.controllers.v1.validate', return_value=True)
    def test_missing_service(self, _):

        # Suppress the expected exception message from service
        body = {'target': 'bogus-service'}
        response = self.app.post_json('/v1/bll', body,
                                      expect_errors=True)
        self.assertEqual(401, response.status_code)
