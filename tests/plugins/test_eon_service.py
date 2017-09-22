# Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# Copyright 2017 SUSE LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from mock import patch

from bll import api
from bll.api.auth_token import TokenHelpers
from bll.api.request import BllRequest
from bll.plugins.eon_service import EONSvc
from tests.util import TestCase, get_mock_token, randomurl, randomidentifier

mock_endpoint = [{'region': randomidentifier(), 'url': randomurl()}]


def mock_call_service(**kwargs):
    path = kwargs['data']['path']

    if path == 'model/entities/networks':
        return [{"name": "VxLAN-R1",
                 "network-group": "VxLAN"}]

    if path == 'model/entities/network-groups':
        return [{"name": "VxLAN",
                 "tags": [{
                     "neutron.networks.vxlan": {
                         "tenant-vxlan-id-range": "1000:2000"}}]}]

    if path == 'model/entities/control-planes':
        return [{'resources': [
                {"name": "kvm-compute",
                 "server-role": "KVM-COMPUTE-ROLE",
                 "service-components": [
                     "nova-compute-kvm",
                     "nova-compute-hyperv"]}]}]

    if path == 'model/entities/server-groups':
        return [{"name": "AZ3", "server-groups": ["RACK3"]},
                {"name": "RACK1"},
                {"name": "RACK2"},
                {"name": "RACK3"}]

    if path == 'model/entities/nic-mappings':
        return [{"name": "HP-DL360-4PORT"},
                {"name": "MY-2PORT-SERVER"}]


class MockEonClient():
    def get_resource_mgr_list(self):
        return {"type": "vcenter"}

    def deactivate_resource(self, id, data):
        pass

    def get_resource_template(self, type, config):
        resp = {
            "input_model": {
                "server_group": "RACK1"
            }
        }
        if type == 'esxcluster':
            return resp
        elif type in ['rhel', 'hyperv', 'hlinux']:
            if type not in ['hyperv']:
                resp['input_model']['nic_mappings'] = []
            resp['input_model']['server_role'] = []
            return resp
        return {}

    def activate_resource(self, id, data):
        return {api.STATUS: api.COMPLETE}

    def get_resource(self, id):
        return {
            'state': 'activated'
        }


def mock_get_client(region=None, url=None):
    return MockEonClient()


class TestEONSvc(TestCase):

    @patch.object(EONSvc, '_get_eon_client', side_effect=mock_get_client)
    @patch.object(EONSvc, 'call_service', side_effect=mock_call_service)
    @patch('bll.plugins.region_client.TokenHelpers.get_endpoints',
           return_value=mock_endpoint)
    def test_prepare_template_fail_no_resource_type(self, *_):

        svc = EONSvc(BllRequest(operation="prepare_activate_template",
                                auth_token=get_mock_token(),
                                data={'data': {}}))

        with self.assertRaisesRegexp(Exception, "Invalid Resource Type"):
            svc.handle()

        body = {'type': 'xyz'}
        svc = EONSvc(BllRequest(operation="prepare_activate_template",
                                auth_token=get_mock_token(),
                                data={'data': body}))

        with self.assertRaisesRegexp(Exception, "Invalid Resource Type"):
            svc.handle()

    @patch.object(EONSvc, '_get_eon_client', side_effect=mock_get_client)
    @patch.object(EONSvc, 'call_service', side_effect=mock_call_service)
    @patch('bll.plugins.region_client.TokenHelpers.get_endpoints',
           return_value=mock_endpoint)
    def test_prepare_activate_template_success_esx(self, *_):
        body = {'type': 'esxcluster'}
        svc = EONSvc(BllRequest(operation="prepare_activate_template",
                                auth_token=get_mock_token(),
                                data={'data': body}))

        reply = svc.handle()
        resp = reply[api.DATA]
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
        self.assertGreater(resp['mgmt_trunk'], 0)
        self.assertGreater(resp['cloud_trunk'], 0)
        self.assertGreater(len(resp['network_names']), 0)

    @patch.object(EONSvc, '_get_eon_client', side_effect=mock_get_client)
    @patch.object(EONSvc, 'call_service', side_effect=mock_call_service)
    @patch('bll.plugins.region_client.TokenHelpers.get_endpoints',
           return_value=mock_endpoint)
    def test_prepare_activate_template_success_hyperv(self, *_):
        body = {'type': 'hyperv'}
        svc = EONSvc(BllRequest(operation="prepare_activate_template",
                                auth_token=get_mock_token(),
                                data={'data': body}))
        reply = svc.handle()
        resp = reply[api.DATA]
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
        self.assertGreater(len(resp['server_roles']), 0)
        self.assertGreater(len(resp['server_groups']), 0)

    @patch.object(EONSvc, '_get_eon_client', side_effect=mock_get_client)
    @patch.object(EONSvc, 'call_service', side_effect=mock_call_service)
    @patch('bll.plugins.region_client.TokenHelpers.get_endpoints',
           return_value=mock_endpoint)
    def test_prepare_activate_template_success_rhel(self, *_):
        body = {'type': 'rhel'}
        svc = EONSvc(BllRequest(operation="prepare_activate_template",
                                auth_token=get_mock_token(),
                                data={'data': body}))
        reply = svc.handle()
        resp = reply[api.DATA]
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
        self.assertGreater(len(resp['server_roles']), 0)
        self.assertGreater(len(resp['server_groups']), 0)
        self.assertGreater(len(resp['nic_mappings']), 0)

    @patch.object(EONSvc, '_get_eon_client', side_effect=mock_get_client)
    @patch.object(EONSvc, 'call_service', side_effect=mock_call_service)
    @patch.object(TokenHelpers, 'get_service_endpoint')
    @patch('bll.plugins.region_client.TokenHelpers.get_endpoints',
           return_value=mock_endpoint)
    def test_activate_resource_success_esx(self, *_):
        body = {
            "type": "esxcluster",
            "network_config": {
                'mgmt_trunk': [{
                    'nics': 'vmnic0',
                    'name': 'MGMT-DVS-SH',
                    'mtu': '1500'
                }],
                'cloud_trunks': [{
                    'nics': 'vmnic1',
                    'network_name': 'VxLAN-R1',
                    'name': 'DATA-DVS', 'mtu': '1500'
                }]
            },
            "id": "12345"
        }
        svc = EONSvc(BllRequest(operation="activate_resource",
                                action="POST",
                                auth_token=get_mock_token(),
                                data={'data': body}))
        svc.handle()
        reply = svc.complete()
        self.assertEqual(reply[api.STATUS], api.COMPLETE)

    @patch.object(EONSvc, '_get_eon_client', side_effect=mock_get_client)
    @patch.object(EONSvc, 'call_service', side_effect=mock_call_service)
    @patch.object(EONSvc, '_validate_resource_state')
    @patch('bll.plugins.region_client.TokenHelpers.get_endpoints',
           return_value=mock_endpoint)
    def test_activate_resource_fail_esx(self, *_):

        body = {"type": "esxcluster", "network_config": {}}
        svc = EONSvc(BllRequest(operation="activate_resource",
                                action="POST",
                                auth_token=get_mock_token(),
                                data={'data': body}))
        svc.handle()
        reply = svc.complete()
        self.assertEqual(reply[api.STATUS], api.STATUS_ERROR)

    @patch.object(EONSvc, '_get_eon_client', side_effect=mock_get_client)
    @patch.object(EONSvc, 'call_service', side_effect=mock_call_service)
    @patch('bll.plugins.region_client.TokenHelpers.get_endpoints',
           return_value=mock_endpoint)
    def test_activate_resource_success_rhel(self, *_):
        body = {
            "type": "rhel",
            "network_config": {
                "nic_mappings": "HP-DL360-4PORT",
                "server_group": "RACK1",
                "server_role": "KVM-COMPUTE-ROLE"
            },
            "id": "12345"
        }
        svc = EONSvc(BllRequest(operation="activate_resource",
                                action="POST",
                                auth_token=get_mock_token(),
                                data={'data': body}))
        svc.handle()
        reply = svc.complete()
        self.assertEqual(reply[api.STATUS], api.COMPLETE)

    @patch.object(EONSvc, '_get_eon_client', side_effect=mock_get_client)
    @patch.object(EONSvc, 'call_service', side_effect=mock_call_service)
    @patch('bll.plugins.region_client.TokenHelpers.get_endpoints',
           return_value=mock_endpoint)
    def test_activate_resource_success_hyperv(self, *_):
        body = {
            "type": "hyperv",
            "network_config": {
                "server_group": "RACK1",
                "server_role": "KVM-COMPUTE-ROLE"
            },
            "id": "12345"
        }
        svc = EONSvc(BllRequest(operation="activate_resource",
                                action="POST",
                                auth_token=get_mock_token(),
                                data={'data': body}))
        svc.handle()
        reply = svc.complete()
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
