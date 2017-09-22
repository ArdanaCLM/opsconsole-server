# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from mock import mock, patch

from tests.util import functional, get_token_from_env, TestCase, randomurl, \
    get_mock_token, randomdict
from bll.common.exception import InvalidBllRequestException
from bll.api.request import BllRequest
from bll import api
from bll.plugins.ardana_service import ArdSvc
from bll.common.job_status import get_job_status


@functional('keystone,ardana')
class ArdanaSvcTest(TestCase):

    def setUp(self):
        self.user = None
        self.token = get_token_from_env()

    def ardana_operation(self, operation=None, path=None, request_data=None,
                         location=None):
        data = {}
        if path:
            data[api.PATH] = path
        if operation:
            data[api.OPERATION] = operation
        if request_data:
            data[api.REQUEST_DATA] = request_data
        if location:
            data['location'] = location
        request = {
            api.ACTION: 'GET',
            api.TARGET: 'ardana',
            api.AUTH_TOKEN: self.token,
            api.DATA: data
        }

        svc = ArdSvc(bll_request=BllRequest(request))
        return svc.handle()

    def test_delete_compute_host_no_input(self):
        with self.assertRaises(Exception):
            self.ardana_operation(operation='delete_compute_host')


class ArdSvcUnitTest(TestCase):
    mock_net_data = {
        'host1': {
            'net_data': {
                'BOND0': {
                    'network1': {
                        'addr': '192.168.1.123',
                        'some': 'data1'
                    },
                    'network2': {
                        'endpoints': {
                            'some': 'moredata'
                        },
                        'blah': 'blah'
                    }
                },
                'eth0': {
                    'network3': {
                        'addr': '192.168.3.123',
                        'some': 'data3'
                    }
                }
            }
        },
        'host2': {
            'net_data': {
                'BOND0': {
                    'network3': {
                        'addr': '192.168.3.231',
                        'some': 'data3'
                    }
                },
                'eth0': {
                    'network1': {
                        'addr': '192.168.3.123',
                        'some': 'data1'
                    }
                }
            }
        },
    }

    @mock.patch('bll.plugins.service.TokenHelpers')
    def test_query_parameters(self, _token_helper):

        base_url = randomurl()
        data = randomdict()
        path = "my/path"

        # The token_helper constructor returns an object with
        # a get_service_endpoint function that we want to override
        _token_helper.return_value.get_service_endpoint.return_value = base_url

        svc = ArdSvc(BllRequest(operation="do_path_operation",
                                auth_token=get_mock_token(),
                                action="GET",
                                data={
                                      'path': path,
                                      'request_data': data,
                                      'request_parameters': ['key=value']
                                  }))

        svc._request = mock.Mock()
        svc.handle()

        # Verify that the proper values are going to be passed to the requests
        # library
        svc._request.assert_called_once_with(path, {"key": "value"}, data,
                                             action='GET')

    @patch('bll.plugins.service.TokenHelpers.get_service_endpoint',
           return_value=randomurl())
    def test_no_playbook(self, *_):
        svc = ArdSvc(BllRequest(operation='run_playbook',
                                auth_token=get_mock_token(),
                                action='POST',
                                data={
                                  }))
        with self.assertRaises(InvalidBllRequestException):
            svc.handle()

    def mock_request(*args, **kwargs):
        class MockResponse:
            def __init__(self, status_code, data):
                self.status_code = status_code
                self.data = data

            def json(self):
                return self.data

        action = args[0]
        url = args[1]
        if action == 'POST' and url.endswith('/playbooks/some_playbook'):
            return MockResponse(200,
                                {
                                    'pRef': 'ref_1',
                                    'alive': True
                                })
        elif action == 'GET':
            # we're now in the non-validate section of handling an is_long
            # function so just pretend we're done
            if url.endswith('model/cp_output/server_info_yml'):
                return MockResponse(200, ArdSvcUnitTest.mock_net_data)
            return MockResponse(200,
                                {
                                    'pRef': 'ref_1',
                                    'alive': False,     # playbook completed
                                    'code': 0           # playbook return code
                                })
        return None

    @patch('bll.plugins.service.TokenHelpers.get_service_endpoint',
           return_value=randomurl())
    @patch('bll.plugins.ardana_service.requests.request',
           side_effect=mock_request)
    def test_playbook_cycle(self, *_):
        svc = ArdSvc(BllRequest(operation='run_playbook',
                                auth_token=get_mock_token(),
                                action='POST',
                                data={
                                      'playbook_name': 'some_playbook',
                                  }))

        # Kick off the playbook
        resp = svc.handle()
        txn_id = resp[api.TXN_ID]

        # We now should be busy running the playbook
        status = get_job_status(txn_id)
        self.assertTrue(status['status'], api.STATUS_INPROGRESS)
        svc.update_job_status()
        self.assertTrue(status['status'], api.STATUS_INPROGRESS)

        # Now pretend we are done
        svc.update_job_status('done', percentage_complete=100, txn_id=txn_id)
        svc.sc_complete()
        self.assertTrue(status['status'], api.COMPLETE)
        self.assertFalse(status[api.DATA]['alive'])
        self.assertEquals(status[api.DATA]['code'], 0)

    @patch('bll.plugins.service.TokenHelpers.get_service_endpoint',
           return_value=randomurl())
    @patch('bll.plugins.ardana_service.requests.request',
           side_effect=mock_request)
    def test_get_network_data(self, *_):
        svc = ArdSvc(BllRequest(operation='get_network_data',
                                  auth_token=get_mock_token()))
        networks = svc.handle()['data']

        # should be 3 networks here
        self.assertEqual(len(networks), 3)
        for network in networks:
            self.assertIsNone(network.get('addr', None))
            self.assertIsNone(network.get('endpoints', None))
