# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from bll.api.auth_token import TokenHelpers
from bll.api.request import BllRequest
from bll import api
from bll.plugins.ironic_service import IronicSvc
from tests.util import TestCase, randomword, randomhex, get_mock_token, \
    randomurl
from ironicclient.v1.node import NodeManager
import mock


class TestIronicSvc(TestCase):

    @mock.patch('bll.plugins.service.SvcBase.call_service',
                return_value={
                    'instances': [{
                        'id': 'instance_1',
                        'status': 'ACTIVE'
                    }, {
                        'id': 'instance_2',
                        'status': 'ACTIVE'
                    }]
                })
    @mock.patch.object(TokenHelpers, 'get_endpoints')
    @mock.patch.object(IronicSvc, '_get_ironic_client')
    def test_baremetal_list(self, _mock_get_func, _mock_endpoints,
                            call_service):
        # this will also indirectly test node.list (generic_list)
        mock_client = mock.MagicMock()
        mock_client.node = mock.create_autospec(NodeManager)

        _mock_endpoints.return_value = [{'region': randomword(),
                                         'url': randomurl()}]

        the_list = [
            self.MockResource(
                {
                    'instance_uuid': 'instance_1',
                    'uuid': randomhex(),
                    'name': randomword(),
                    'power_state': 'power on'
                }),
            self.MockResource(
                {
                    'instance_uuid': 'instance_2',
                    'uuid': randomhex(),
                    'name': randomword(),
                    'power_state': 'power on'
                })]
        mock_client.node.list.return_value = the_list
        _mock_get_func.return_value = mock_client

        svc = IronicSvc(BllRequest(operation='baremetal-list',
                                   auth_token=get_mock_token()))

        data = svc.handle()[api.DATA]
        self.assertEqual(len(data), 2)
        for inst in data:
            self.assertTrue('baremetal', 'compute' in inst.keys())
            self.assertTrue(inst['baremetal']['instance_uuid'] ==
                            inst['compute']['id'])

    @mock.patch.object(IronicSvc, '_get_ironic_client')
    @mock.patch.object(TokenHelpers, 'get_endpoints')
    def test_generic_get(self, _mock_endpoints, _mock_get_func):
        mock_client = mock.MagicMock()
        mock_client.node = mock.create_autospec(NodeManager)

        _mock_endpoints.return_value = [{'region': randomword(),
                                         'url': randomurl()}]

        nodeid = randomhex()
        res = self.MockResource(
            {
                'instance_uuid': randomhex(),
                'uuid': nodeid,
                'driver': 'agent_ilo',
                'name': randomword(),
                'power_state': 'power on',
                'provision_state': 'active',
            })
        mock_client.node.get.return_value = res
        _mock_get_func.return_value = mock_client

        svc = IronicSvc(BllRequest(operation='node.get',
                                   auth_token=get_mock_token(),
                                   data={'node_id': randomhex}))

        data = svc.handle()[api.DATA]
        self.assertIsInstance(data, dict)
        self.assertEqual(data['driver'], 'agent_ilo')
        self.assertEqual(data['uuid'], nodeid)

    class MockResource():
        data = {}

        def __init__(self, data):
            self.data = data

        def to_dict(self):
            return self.data
