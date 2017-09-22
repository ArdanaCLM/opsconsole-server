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

from bll import api
from bll.api.auth_token import TokenHelpers
from bll.api.request import BllRequest
from bll.plugins import compute_service
from mock import patch
from tests.util import TestCase, get_mock_token, randomurl
from random import random

import mock
import copy


def call_service_test_utilization(target=None, operation=None, data=None):
    if not operation:
        operation = data['operation']
    hosts = ['host1', 'host2', 'host3']
    if target == 'catalog' and operation == 'get_compute_clusters':
        return {
            'ccp:compute': hosts
        }
    elif target == 'monitor' and operation == 'measurement_list':
        metric_name = data['name']
        meas_list = []
        if '_perc' in metric_name:
            for host in hosts:
                meas_list.append(
                    get_meas(host, float('%.1f' % (random() * 100))))
        elif '_mb' in metric_name:
            if 'total' in metric_name:
                for host in hosts:
                    meas_list.append(get_meas(host, float('%.1f' % 8192)))
            else:
                for host in hosts:
                    meas = get_meas(host, float('%.1f' % (random() * 8192)))
                    meas_list.append(meas)
        return meas_list
    elif target == 'nova' and operation == 'hypervisor-list':
        return [
            {
                'hypervisor_id': 1,
                'name': 'host1',
                'hypervisor_hostname': 'host1',
                'service_host': 'host1',
            },
            {
                'hypervisor_id': 2,
                'name': 'host2',
                'hypervisor_hostname': 'host2',
                'service_host': 'host2',
            },
            {
                'hypervisor_id': 3,
                'name': 'host3',
                'hypervisor_hostname': 'host3',
                'service_host': 'host3',
            }
        ]


def call_service_test_details(target=None, data=None, operation=None,
                              path=None):
    hostname = 'some_name'
    cp_host_name = 'test_cp_host'
    if target == 'nova' and operation == 'hypervisor-list':
        return [
            {
                'hypervisor_id': 1,
                'instances': 2,
                'name': hostname
            }
        ]
    elif target == 'monitor' and data['operation'] == 'measurement_list':
        return [
            {
                'columns': ['timestamp', 'value', 'value_meta'],
                'measurements': [['some_data_string', 123]]
            }
        ]
    elif target == 'ardana':
        if path == '/model/cp_output/server_info.yml':
            return {
                cp_host_name: {
                    'hostname': hostname
                }
            }
        elif path == '/model/entities/servers/' + cp_host_name:
            return {
                'id': cp_host_name,
                'role': 'some_role',
                'server-group': 'some_group'
            }


def get_meas(host, value):
    meas_template = {
        'columns': ['timestamp', 'value', 'value_meta'],
        'measurements': [['some_time', 'some_value', {}]],
        'dimensions': {'hostname': 'some_host'}
    }
    value_idx = meas_template['columns'].index('value')
    meas = copy.deepcopy(meas_template)
    meas['measurements'][-1][value_idx] = value
    meas['dimensions']['hostname'] = host
    return meas


def call_service(target=None, operation=None, region=None,
                 data=None):
    if target == 'nova' and operation == 'hypervisor-allocation-stats':
        return {
            1: {
                "allocated_cpu": 0,
                "allocated_memory": 2816,
                "allocated_storage": 10,
                "instances": 0,
                "total_cpu": 32.0,
                "total_memory": 252198.0,
                "total_storage": 1110
            }
        }
    elif target == 'nova' and operation == 'hypervisor-list':
        return [
            {
                "allocated_cpu": 0,
                "allocated_memory": 2816,
                "allocated_storage": 10,
                "hypervisor_id": 1,
                "instances": 0,
                "hypervisor_hostname":
                    "domain-c84.68bb08ca-07ed-4b9d-835f-1815a5f15a85",
                "ping_status": "up",
                "service_host": "some_host",
                "region": "my_region",
                "state": "up",
                "status": "enabled",
                "total_cpu": 32,
                "total_memory": 252198,
                "total_storage": 1110,
                "type": "VMware vCenter Server"
            }
        ]
    elif target == 'eon' and operation == 'resource_list':
        return [
            {
                "hypervisor_id": "1",
                "instances": 0,
                "hypervisor_hostname":
                    "domain-c84.68bb08ca-07ed-4b9d-835f-1815a5f15a85",
                "ping_status": "up",
                "region": "my_region",
                "service_host": "some_host",
                "state": "up",
                "status": "enabled",
                "type": "VMware vCenter Server"
            }
        ]


class TestComputeSvc(TestCase):

    @patch.object(TokenHelpers, 'get_service_endpoint',
                  return_value=randomurl())
    @patch('bll.plugins.service.SvcBase.call_service',
           side_effect=call_service)
    def test_get(self, *_):

        svc = compute_service.ComputeSvc(BllRequest(
            action='GET',
            operation='get_compute_list',
            auth_token=get_mock_token()))

        svc._update_eon_with_monasca_status = mock.Mock()

        reply = svc.handle()
        self.assertEqual(api.COMPLETE, reply[api.STATUS])
        self.assertEqual(1, len(reply['data']))

    def test_filter_out_hosts(self):
        compute_list = [{
            'name': 'hostkvm',
            'type': 'kvm'
        }, {
            'name': 'hostironic',
            'type': 'ironic'
        }, {
            'name': 'hostqemu',
            'type': 'qemu'
        }]

        # filter out hosts with type set to ironic
        hosts = compute_service.ComputeSvc._filter_out_hosts(compute_list,
                                                             'type', 'ironic')

        self.assertEqual(2, len(hosts))
        for host in hosts:
            self.assertNotEqual(host['type'], 'ironic')

    @patch('bll.api.auth_token.TokenHelpers.get_service_endpoint',
           return_value=True)
    def test_get_resource_details(self, *_):
        request = {
            api.TARGET: 'compute',
            api.ACTION: 'GET',
            api.AUTH_TOKEN: get_mock_token(),
            api.DATA: {
                api.OPERATION: 'details',
                api.VERSION: 'v1',
                api.DATA: {
                    "id": "e90f7f6f-c75f-4830-8f47-e0af2851b132",
                    "type": "esxcluster"
                }
            }
        }

        svc = compute_service.ComputeSvc(bll_request=BllRequest(request))
        # Mock out invocations of call_service
        svc.call_service = mock.MagicMock()
        reply = svc.handle()
        self.assertEqual(reply[api.STATUS], api.COMPLETE)

    @patch('bll.plugins.service.SvcBase.call_service',
           side_effect=call_service)
    @patch('bll.api.auth_token.TokenHelpers.get_service_endpoint',
           return_value=True)
    def test_update_eon_with_stats(self, *_):
        # example of what comes back from eon
        compute_list = [
            {
                "cluster_moid": "domain-c84",
                "id": "ebe3e327-1e02-4feb-bfed-7eaa410bb5c9",
                "ip_address": "UNSET",
                "meta_data": [
                    {
                        "id": "311c3abc-15c6-4156-bf61-38ea304e8675",
                        "name": "hypervisor_id",
                        "value": "1"
                    },
                    {
                        "id": "7063a114-469f-4591-8315-e042801235ca",
                        "name": "network_properties",
                        "value": "network_properties_blah"
                    },
                    {
                        "id": "7173ccad-c4c7-4b76-b1e9-91b6da330af6",
                        "name": "cluster_moid",
                        "value": "domain-c3135"
                    },
                    {
                        "id": "ca70eaac-8bd9-411d-9c98-d90d7812b5a1",
                        "name": "ardana_properties",
                        "value": "ardana_properties_blah"
                    }
                ],
                "hypervisor_hostname":
                    "domain-c84.68bb08ca-07ed-4b9d-835f-1815a5f15a85",
                "name": "Compute-08A",
                "password": "UNSET",
                "port": "UNSET",
                "region": "my_region",
                "resource_mgr_id": "68bb08ca-07ed-4b9d-835f-1815a5f15a85",
                "state": "activated",
                "type": "esxcluster",
                "username": "UNSET"
            }
        ]

        request = {
            api.TARGET: 'compute',
            api.ACTION: 'GET',
            api.AUTH_TOKEN: 'blah',
            api.DATA: {
                api.OPERATION: 'get_compute_list'
            }
        }

        svc = compute_service.ComputeSvc(bll_request=BllRequest(request))
        svc._filter_eon_compute_node = mock.Mock(return_value=compute_list)

        reply = svc.handle()
        self.assertEqual(api.COMPLETE, reply[api.STATUS])
        self.assertFalse('meta_data' in reply[api.DATA][0])
        self.assertEquals(reply[api.DATA][0]['network_properties'],
                          'network_properties_blah')
        self.assertEquals(reply[api.DATA][0]['ping_status'], 'up')

    @patch('bll.api.auth_token.TokenHelpers.get_service_endpoint',
           return_value=randomurl())
    def test_get_compute_details_legacy(self, *_):
        request = {
            api.TARGET: 'compute',
            api.ACTION: 'GET',
            api.AUTH_TOKEN: get_mock_token(),
            api.DATA: {
                api.OPERATION: 'get_compute_list',
                api.VERSION: 'v1',
                api.DATA: {
                    "id": "e90f7f6f-c75f-4830-8f47-e0af2851b132",
                    "hypervisor": "esxcluster",
                    "hypervisor_id": "1"
                }
            }
        }
        svc = compute_service.ComputeSvc(
            bll_request=BllRequest(request))
        svc.call_service = mock.Mock(return_value=[])
        reply = svc.handle()
        self.assertEqual(api.COMPLETE, reply[api.STATUS])

    @patch.object(TokenHelpers, 'get_service_endpoint', return_value=None)
    def test_get_compute_details_stdcfg(self, a):
        request = {
            api.TARGET: 'compute',
            api.ACTION: 'GET',
            api.AUTH_TOKEN: get_mock_token(),
            api.DATA: {
                api.OPERATION: 'get_compute_list',
                api.VERSION: 'v1',
                api.DATA: {
                    "id": "e90f7f6f-c75f-4830-8f47-e0af2851b132",
                    "hypervisor": "esxcluster",
                    "hypervisor_id": "1"
                }
            }
        }
        svc = compute_service.ComputeSvc(bll_request=BllRequest(request))
        svc.call_service = mock.Mock(return_value=[])
        reply = svc.handle()
        self.assertEqual(api.COMPLETE, reply[api.STATUS])

    @patch.object(TokenHelpers, 'get_service_endpoint', return_value=None)
    @patch('bll.plugins.service.SvcBase.call_service',
           side_effect=call_service_test_utilization)
    def test_get_cluster_utilization(self, *_):
        request = {
            api.TARGET: 'compute',
            api.ACTION: 'GET',
            api.AUTH_TOKEN: get_mock_token(),
            api.DATA: {
                api.OPERATION: 'get_cluster_utilization'
            }
        }
        svc = compute_service.ComputeSvc(bll_request=BllRequest(request))
        reply = svc.handle()
        self.assertEqual(api.COMPLETE, reply[api.STATUS])
        data = reply[api.DATA]
        self.assertTrue('ccp:compute' in data)

        # 3 hosts
        self.assertEqual(len(data['ccp:compute']), 3)

        self.assertTrue('host1' in data['ccp:compute'])
        self.assertTrue('used_memory_perc' in data['ccp:compute']['host1'])
        self.assertTrue('used_storage_perc' in data['ccp:compute']['host1'])
        self.assertTrue('used_cpu_perc' in data['ccp:compute']['host1'])

    @patch('bll.api.auth_token.TokenHelpers.get_service_endpoint',
           return_value=True)
    @patch('bll.plugins.service.SvcBase.call_service',
           side_effect=call_service_test_details)
    def test_get_non_eon_details(self, *_):
        svc = compute_service.ComputeSvc(BllRequest(
            auth_token=get_mock_token(),
            operation='details',
            region='region1',
            data={
                'data': {
                    'id': '1',
                    'type': 'kvm'
                }
            }))

        reply = svc.handle()
        self.assertEqual(reply['data']['ardana']['server-group'], 'some_group')
        self.assertEqual(reply['data']['monasca']['used_cpu_perc'], 123)
        self.assertEqual(reply['data']['instances'], 2)
        self.assertEqual(reply[api.STATUS], api.COMPLETE)
