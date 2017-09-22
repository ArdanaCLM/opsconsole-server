# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

from datetime import timedelta, date
from random import randint
import random
import logging

import mock
from mock import patch, MagicMock, Mock

from bll import api
from bll.api.request import BllRequest
from bll.plugins.nova_service import NovaSvc, power_states
from bll.plugins.user_group_service import UserGroupSvc
from bll.plugins.monitor_service import MonitorSvc
from bll.api.auth_token import TokenHelpers
import novaclient.client as nclient
from keystoneclient.v3 import client as ksclient
from monascaclient import client as msclient
from tests.util import TestCase, randomword, randomip, \
    functional, get_token_from_env, log_level, get_mock_token


class Flavor():
    # Generate a mostly random flavor

    def __init__(self):
        self.id = randomword()
        self.name = randomword()
        self.vcpus = 2 ** randint(0, 3)
        self.ram = 1024 * randint(1, 16)
        self.disk = 1000 * randint(1, 8)


class Server():
    # Generate a mostly random server

    def __init__(self, name=None, image_id=None, power_state=None,
                 flavor_id=None, metadata=None, tenant_id=None):
        self.name = name or randomword()
        self.id = randomword()
        self.metadata = metadata
        self.status = randomword()
        self._info = {
            'OS-EXT-SRV-ATTR:host': randomword(),
            'OS-EXT-STS:power_state': power_state,
            'OS-EXT-AZ:availability_zone': randomword(),
            'OS-EXT-STS:task_state': randomword()}
        self.image = {'id': image_id}
        self.addresses = randomword()
        self.created = None
        self.key_name = randomword()
        self.flavor = {'id': flavor_id}
        self.tenant_id = tenant_id


class Hypervisor():
    def __init__(self):
        self.vcpus_used = randint(0, 4)
        self.vcpus = randint(0, 4)
        self.memory_mb_used = randint(1024, 2048)
        self.memory_mb = randint(4096, 8192)
        self.local_gb_used = randint(1, 5)
        self.local_gb = randint(10, 20)
        self.running_vms = randint(0, 4)
        self.NAME_ATTR = 'hypervisor_hostname'
        self.hypervisor_hostname = 'testhost-%s' % randomword()
        self.host_ip = randomip()
        self.id = randint(1, 10000)
        self.status = 'enabled'
        self.state = 'up'
        self.hypervisor_type = 'QEMU'
        self.service = {'host': self.hypervisor_hostname}


class Struct(object):
    """
    Convert dictionary to object
    From
      http://stackoverflow.com/questions/1305532/convert-python-dict-to-object
    """

    def __init__(self, data):
        for name, value in data.iteritems():
            setattr(self, name, self._wrap(value))

    def _wrap(self, value):
        if isinstance(value, (tuple, list, set, frozenset)):
            return type(value)([self._wrap(v) for v in value])
        else:
            return Struct(value) if isinstance(value, dict) else value


class TestNovaSvc(TestCase):

    def setUp(self):
        self.flavor_list = []
        for x in range(5):
            self.flavor_list.append(Flavor())

        self.image_list = [Struct({'id': '1', 'name': 'cirros'})]

        self.project_list = [
            Struct({'id': '1', 'name': 'default_project'}),
            Struct({'id': '2', 'name': 'admin_project'})
        ]

        self.hyp_list = []
        for x in range(4):
            self.hyp_list.append(Hypervisor())

        self.mock_novaclient = MagicMock(spec=nclient.Client)
        self.mock_novaclient.flavors = Mock(**{
            'list.return_value': self.flavor_list})
        self.mock_novaclient.images = Mock(**{
            'list.return_value': self.image_list})
        self.mock_novaclient.hypervisors = Mock(**{
            'list.return_value': self.hyp_list})

        self.server_list = []

        self.server_list.append(Server(
            name=randomword(),
            flavor_id=random.choice(self.flavor_list).id,
            image_id=random.choice(self.image_list).id,
            power_state=random.choice(power_states.keys()),
            metadata={'monitor': 'true'},
            tenant_id=self.project_list[1].id))

        # project node
        self.server_list.append(Server(
            name=randomword(),
            flavor_id=random.choice(self.flavor_list).id,
            image_id=random.choice(self.image_list).id,
            power_state=random.choice(power_states.keys()),
            metadata={},
            tenant_id=self.project_list[0].id))

        self.services_list = [Struct({'id': '1', 'host': 'myhost1'})]

        self.mock_novaclient.servers = Mock(**{
            'list.return_value': self.server_list})

        self.mock_novaclient.services = Mock(**{
            'list.return_value': self.services_list,
            'delete.return_value': 'Pass'
        })

        self.mock_ksclient = MagicMock(spec=ksclient.Client)
        self.mock_ksclient.projects = Mock(**{
            'list.return_value': self.project_list
        })

        self.mock_monasca_client = MagicMock(spec=msclient.Client)
        self.mock_monasca_client.metrics = Mock(**{
            'list_statistics.return_value': [{
                "name": "some.metric",
                "statistics": [
                    ["2016-07-12T19:16:00.000Z", 31],
                    ["2016-07-12T19:17:00.000Z", 31],
                ],
                "dimensions": {},
                "columns": ["timestamp", "avg"],
                "id": "682bec4c92f43a52fd4f3a2855c2a026b27a063d"
            }],
            'list_measurements.return_value': [{
                "name": "some.metric",
                "measurements": [
                    ["2016-07-12T19:16:00.000Z", 10],
                    ["2016-07-12T19:17:00.000Z", 10],
                ],
                "dimensions": {},
                "columns": ["timestamp", "avg"],
                "id": "682bec4c92f43a52fd4f3a2855c2a026b27a063d"
            }]
        })

        self.mock_get_endpoints = [{'region': None, 'url': None}]

    @mock.patch.object(UserGroupSvc, '_get_ks_client')
    @mock.patch.object(TokenHelpers, 'get_service_endpoint')
    @mock.patch.object(TokenHelpers, 'get_endpoints')
    @mock.patch.object(NovaSvc, '_get_nova_client')
    def test_full_instance_list(self,
                                _mock_nova_client,
                                _mock_endpoints,
                                _mock_serv_end,
                                _mock_ks_client):
        _mock_nova_client.return_value = self.mock_novaclient

        # Pretend the baremetal endpoint does not exist
        _mock_serv_end.return_value = None
        _mock_endpoints.return_value = self.mock_get_endpoints

        # Pretend there's one tenant called "some_tenant"
        _mock_ks_client.return_value = self.mock_ksclient

        svc = NovaSvc(BllRequest(auth_token=get_mock_token(),
                                 data={api.OPERATION: 'instance-list'}))

        reply = svc.handle()
        self.assertEqual(api.COMPLETE, reply[api.STATUS])
        self.assertEqual(
            len(self.server_list), len(reply[api.DATA]['instances']))

    @mock.patch.object(UserGroupSvc, '_get_ks_client')
    @mock.patch.object(TokenHelpers, 'get_service_endpoint')
    @mock.patch.object(TokenHelpers, 'get_endpoints')
    @mock.patch.object(NovaSvc, '_get_nova_client')
    def test_hypervisor_list(self,
                             _mock_nova_client,
                             _mock_endpoints,
                             _mock_serv_end,
                             _mock_ks_client):
        _mock_nova_client.return_value = self.mock_novaclient
        _mock_serv_end.return_value = None
        _mock_ks_client.return_value = self.mock_ksclient
        _mock_endpoints.return_value = self.mock_get_endpoints

        svc = NovaSvc(BllRequest(auth_token=get_mock_token(),
                                 data={api.OPERATION: 'hypervisor-list'}))

        # build up a list of ping statuses
        statuses = {}
        for hyp in self.hyp_list:
            statuses[hyp.hypervisor_hostname] = 'up'

        with patch('bll.plugins.service.SvcBase.call_service',
                   return_value=statuses):
            reply = svc.handle()

        self.assertEqual(api.COMPLETE, reply[api.STATUS])

        # 4 hypervisors
        hyp_list = reply[api.DATA]
        self.assertEqual(len(self.hyp_list), len(hyp_list))
        known_id_list = [x.id for x in self.hyp_list]
        for hyp in hyp_list:
            self.assertTrue(hyp['hypervisor_id'] in known_id_list)
            self.assertEqual(hyp['ping_status'], 'up')

    def nova_operation(self, operation, data=None):
        request = {
            api.TARGET: 'nova',
            api.AUTH_TOKEN: self.token or None,
            api.DATA: {
                api.OPERATION: operation
            }
        }
        if data:
            request[api.DATA].update(data)

        svc = NovaSvc(bll_request=BllRequest(request))
        return svc.handle()

    @functional('nova')
    def test_instance_list(self):
        self.token = get_token_from_env()

        reply = self.nova_operation('instance-list')
        self.assertEqual(api.COMPLETE, reply[api.STATUS])
        self.assertIn('instances', reply[api.DATA])

    @functional('nova')
    def test_service_list(self):
        self.token = get_token_from_env()

        reply = self.nova_operation('service-list')
        self.assertEqual(api.COMPLETE, reply[api.STATUS])
        self.assertIn('total', reply[api.DATA])
        self.assertIn('ok', reply[api.DATA])
        self.assertIn('error', reply[api.DATA])

    @functional('nova')
    def test_servers_list(self):
        self.token = get_token_from_env()

        end_date = date.today()
        start_date = end_date + timedelta(-1)

        reply = self.nova_operation('servers-list', {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
        })
        self.assertEqual(api.COMPLETE, reply[api.STATUS])
        self.assertIn('created', reply[api.DATA])
        self.assertIn('deleted', reply[api.DATA])

    @functional('nova')
    def test_hypervisor_stats(self):
        self.token = get_token_from_env()

        reply = self.nova_operation('hypervisor-stats')
        self.assertEqual(api.COMPLETE, reply[api.STATUS])
        self.assertIn('total', reply[api.DATA])
        self.assertIn('used', reply[api.DATA])

    @mock.patch.object(UserGroupSvc, '_get_ks_client')
    @mock.patch.object(TokenHelpers, 'get_service_endpoint')
    @mock.patch.object(NovaSvc, '_get_nova_client')
    def test_service_delete_no_input(self,
                                     _mock_nova_client,
                                     _mock_serv_end,
                                     _mock_ks_client):
        _mock_nova_client.return_value = self.mock_novaclient
        _mock_serv_end.return_value = None
        _mock_ks_client.return_value = self.mock_ksclient

        with log_level(logging.CRITICAL, 'bll'):
            svc = NovaSvc(BllRequest(auth_token=get_mock_token(),
                                     data={api.OPERATION: 'service-delete'}))
            # In production the service is called via the handle method of the
            # base, SvcBase, which uses pykka and catches exceptions and
            # returns an appropriate error response to the caller.  But using
            # pykka in unit tests conflicts with the mock library causing any
            # such tests to hang as both libraries are attempting to
            # automagically wrap function calls in proxies.  Therefore we have
            # to directly expect and handle the exception ourselves.
            with self.assertRaises(Exception):
                svc.handle()

    @mock.patch.object(UserGroupSvc, '_get_ks_client')
    @mock.patch.object(TokenHelpers, 'get_service_endpoint')
    @mock.patch.object(TokenHelpers, 'get_endpoints')
    @mock.patch.object(NovaSvc, '_get_nova_client')
    def test_service_delete_bad_input(self,
                                      _mock_nova_client,
                                      _mock_endpoints,
                                      _mock_serv_end,
                                      _mock_ks_client):
        _mock_nova_client.return_value = self.mock_novaclient
        _mock_serv_end.return_value = None
        _mock_ks_client.return_value = self.mock_ksclient
        _mock_endpoints.return_value = self.mock_get_endpoints

        with log_level(logging.CRITICAL, 'bll'):
            svc = NovaSvc(BllRequest(auth_token=get_mock_token(),
                                     operation='service-delete',
                                     data={'hostname': 'badhost'}))
            with self.assertRaises(Exception):
                svc.handle()

    @mock.patch.object(UserGroupSvc, '_get_ks_client')
    @mock.patch.object(TokenHelpers, 'get_service_endpoint')
    @mock.patch.object(TokenHelpers, 'get_endpoints')
    @mock.patch.object(NovaSvc, '_get_nova_client')
    def test_service_delete_good_input(self,
                                       _mock_nova_client,
                                       _mock_endpoints,
                                       _mock_serv_end,
                                       _mock_ks_client):
        _mock_nova_client.return_value = self.mock_novaclient
        _mock_serv_end.return_value = None
        _mock_ks_client.return_value = self.mock_ksclient
        _mock_endpoints.return_value = self.mock_get_endpoints

        svc = NovaSvc(BllRequest(auth_token=get_mock_token(),
                                 operation='service-delete',
                                 data={'hostname': 'myhost1'}))
        reply = svc.handle()
        self.assertEqual(reply[api.STATUS], api.COMPLETE)

    @mock.patch.object(UserGroupSvc, '_get_ks_client')
    @mock.patch.object(TokenHelpers, 'get_service_endpoint')
    @mock.patch.object(TokenHelpers, 'get_endpoints')
    @mock.patch.object(MonitorSvc, '_get_monasca_client')
    @mock.patch.object(NovaSvc, '_get_nova_client')
    def test_service_inc_metrics_statistics(self,
                                            _mock_nova_client,
                                            _mock_monasca_client,
                                            _mock_endpoints,
                                            _mock_serv_end,
                                            _mock_ks_client):
        _mock_nova_client.return_value = self.mock_novaclient
        _mock_serv_end.return_value = None
        _mock_ks_client.return_value = self.mock_ksclient
        _mock_monasca_client.return_value = self.mock_monasca_client
        _mock_endpoints.return_value = self.mock_get_endpoints

        req_data = {
            api.OPERATION: 'instance-list',
            'monasca_metrics': ['some.metric'],
            'monasca_data': {
                'operation': 'metric_statistics'
            }
        }

        svc = NovaSvc(BllRequest(auth_token=get_mock_token(),
                                 data=req_data))
        reply = svc.handle()
        self.assertEqual(reply[api.STATUS], api.COMPLETE)

        self.mock_monasca_client.metrics.list_statistics.assert_called_with(
            name='some.metric'
        )

        self.assertIn(api.DATA, reply)
        data = reply[api.DATA]
        self.assertIn('instances', data)
        self.assertIsInstance(data['instances'], list)
        self.assertTrue(len(data['instances']) > 0)
        self.assertIn('metrics', data['instances'][0])
        self.assertIn('some.metric', data['instances'][0]['metrics'])
        some_metric = data['instances'][0]['metrics']['some.metric']
        self.assertEquals(some_metric[0]['statistics'][0][1], 31)

    @mock.patch.object(UserGroupSvc, '_get_ks_client')
    @mock.patch.object(TokenHelpers, 'get_service_endpoint')
    @mock.patch.object(TokenHelpers, 'get_endpoints')
    @mock.patch.object(MonitorSvc, '_get_monasca_client')
    @mock.patch.object(NovaSvc, '_get_nova_client')
    def test_service_inc_metrics_measurements(self,
                                              _mock_nova_client,
                                              _mock_monasca_client,
                                              _mock_endpoints,
                                              _mock_serv_end,
                                              _mock_ks_client):
        _mock_nova_client.return_value = self.mock_novaclient
        _mock_serv_end.return_value = None
        _mock_ks_client.return_value = self.mock_ksclient
        _mock_monasca_client.return_value = self.mock_monasca_client
        _mock_endpoints.return_value = self.mock_get_endpoints

        req_data = {
            api.OPERATION: 'instance-list',
            'monasca_metrics': ['some.metric'],
            'monasca_data': {
                'operation': 'measurement_list'
            }
        }

        svc = NovaSvc(BllRequest(auth_token=get_mock_token(),
                                 data=req_data))
        reply = svc.handle()
        self.assertEqual(reply[api.STATUS], api.COMPLETE)

        self.mock_monasca_client.metrics.list_measurements \
            .assert_called_with(
                name='some.metric'
            )

        self.assertIn(api.DATA, reply)
        data = reply[api.DATA]
        self.assertIn('instances', data)
        self.assertIsInstance(data['instances'], list)
        self.assertTrue(len(data['instances']) > 0)
        self.assertIn('metrics', data['instances'][0])
        self.assertIn('some.metric', data['instances'][0]['metrics'])
        some_metric = data['instances'][0]['metrics']['some.metric']
        self.assertEquals(some_metric[0]['measurements'][0][1], 10)

        @mock.patch.object(UserGroupSvc, '_get_ks_client')
        @mock.patch.object(TokenHelpers, 'get_service_endpoint')
        @mock.patch.object(TokenHelpers, 'get_endpoints')
        @mock.patch.object(MonitorSvc, '_get_monasca_client')
        @mock.patch.object(NovaSvc, '_get_nova_client')
        def test_service_inc_metrics_dimension_prop(self,
                                                    _mock_nova_client,
                                                    _mock_monasca_client,
                                                    _mock_endpoints,
                                                    _mock_serv_end,
                                                    _mock_ks_client):
            _mock_nova_client.return_value = self.mock_novaclient
            _mock_serv_end.return_value = None
            _mock_ks_client.return_value = self.mock_ksclient
            _mock_monasca_client.return_value = self.mock_monasca_client
            _mock_endpoints.return_value = self.mock_get_endpoints

            req_data = {
                api.OPERATION: 'instance-list',
                'project_id': self.project_list[0].id,
                'monasca_metrics': ['some.metric'],
                'monasca_dimensions': {
                    'resource_id': {
                        'property': 'tenant_id'
                    }
                },
                'monasca_data': {
                    'operation': 'metric_statistics'
                }
            }

            svc = NovaSvc(BllRequest(auth_token=get_mock_token(),
                                     data=req_data))
            reply = svc.handle()
            self.assertEqual(reply[api.STATUS], api.COMPLETE)

            self.mock_monasca_client.metrics.list_statistics \
                .assert_called_with(
                    name='some.metric',
                    dimensions={
                        'resource_id': self.server_list[4].id
                    }
                )

            self.assertIn(api.DATA, reply)
            data = reply[api.DATA]
            self.assertIn('instances', data)
            self.assertIsInstance(data['instances'], list)
            self.assertTrue(len(data['instances']) > 0)
            self.assertIn('metrics', data['instances'][0])
            self.assertIn('some.metric', data['instances'][0]['metrics'])

        @mock.patch.object(UserGroupSvc, '_get_ks_client')
        @mock.patch.object(TokenHelpers, 'get_service_endpoint')
        @mock.patch.object(TokenHelpers, 'get_endpoints')
        @mock.patch.object(MonitorSvc, '_get_monasca_client')
        @mock.patch.object(NovaSvc, '_get_nova_client')
        def test_service_inc_metrics_dimension(self,
                                               _mock_nova_client,
                                               _mock_monasca_client,
                                               _mock_endpoints,
                                               _mock_serv_end,
                                               _mock_ks_client):
            _mock_nova_client.return_value = self.mock_novaclient
            _mock_serv_end.return_value = None
            _mock_ks_client.return_value = self.mock_ksclient
            _mock_monasca_client.return_value = self.mock_monasca_client
            _mock_endpoints.return_value = self.mock_get_endpoints

            req_data = {
                api.OPERATION: 'instance-list',
                'project_id': self.project_list[0].id,
                'monasca_metrics': ['some.metric'],
                'monasca_dimensions': {
                    'cluster': 'compute'
                },
                'monasca_data': {
                    'operation': 'metric_statistics'
                }
            }

            svc = NovaSvc(BllRequest(auth_token=get_mock_token(),
                                     data=req_data))
            reply = svc.handle()
            self.assertEqual(reply[api.STATUS], api.COMPLETE)

            self.mock_monasca_client.metrics.list_statistics \
                .assert_called_with(
                    name='some.metric',
                    dimensions={
                        'cluster': 'compute'
                    }
                )

            self.assertIn(api.DATA, reply)
            data = reply[api.DATA]
            self.assertIn('instances', data)
            self.assertIsInstance(data['instances'], list)
            self.assertTrue(len(data['instances']) > 0)
            self.assertIn('metrics', data['instances'][0])
            self.assertIn('some.metric', data['instances'][0]['metrics'])
