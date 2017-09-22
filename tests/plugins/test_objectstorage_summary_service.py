# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from mock import patch
from bll import api
from bll.api.auth_token import TokenHelpers
from bll.api.request import BllRequest
from bll.plugins import objectstorage_summary_service
from monascaclient.v2_0.alarms import AlarmsManager
from monascaclient.v2_0.metrics import MetricsManager
from monascaclient.v2_0.alarm_definitions import AlarmDefinitionsManager

from tests.util import TestCase

MEASUREMENT_OUPUT = [{'dimensions':
                      {'service': 'ops-console',
                       'cluster': 'management',
                       'url': 'http://192.16.66.10:9095/version.json',
                       'hostname': 'mycloud-ccp-mgmt-m1-clm',
                       'component': 'ops-console-web',
                       'control_plane': 'ccp',
                       'mount': '/dev/mqueue',
                       'cloud_name': 'mycloud'
                       },
                      'measurements': [['2016-08-28T22:41:15.000Z', 12.0, {}],
                                       ['2016-08-28T23:41:15.000Z', 59.0, {}]
                                       ],
                      'id': '3a155502224c8e83b30ee13e2adfe9d89d78e602',
                      'columns': ['timestamp', 'value', 'value_meta'],
                      'name': 'test'}]

STATISTICS_OUTPUT = [{'dimensions':
                      {'service': 'object-storage',
                       'cluster': 'MyCluster',
                       'hostname': 'MyHostname',
                       'mount': '/dev/mqueue'
                       },
                      'name': 'Swiftlm.Test',
                      'statistics': [
                          ['2016-08-27T23:41:15.000Z', 26.9],
                          ['2016-07-28T07:41:15.000Z', 0.0],
                          ['2016-07-28T11:41:15.000Z', 34.5],
                          ['2016-07-28T19:41:15.000Z', 34.5],
                          ['2016-08-28T23:41:15.000Z', 2.0]]
                      }
                     ]

SPECIAL_STATISTICS_OUTPUT = [{'dimensions':
                              {'service': 'object-storage',
                               'cluster': 'MyCluster',
                               'hostname': 'MyHostname',
                               'mount': '/dev/mqueue'
                               },
                              'name': 'Swiftlm.Test',
                              'statistics': [
                                  ['2016-08-27T23:41:15.000Z', 26.9],
                                  ['2016-07-28T04:41:15.000Z', 2.0],
                                  ['2016-07-28T07:41:15.000Z', 0.0],
                                  ['2016-07-28T11:41:15.000Z', 34.5],
                                  ['2016-07-28T15:41:15.000Z', 0.0],
                                  ['2016-07-28T19:41:15.000Z', 34.5],
                                  ['2016-08-28T23:41:15.000Z', 2.0]]
                              }
                             ]

ALARM_DEFINITION_SHOW_OUTPUT = {'description': 'Alarms',
                                'id': '38b3c2b7-efe6',
                                'name': 'Disk Usage',
                                'severity': 'LOW'
                                }

ALARM_LIST_OUTPUT = [{'state': 'OK',
                      'alarm_definition': {'severity': 'LOW',
                                           'id': '38b3c2b7-efe6',
                                           'name': 'Disk Usage'},
                      'id': 'ff43aacc-a5db-4f6f-a5d3-44f9cce8c713'},
                     {'state': 'ALARM',
                      'alarm_definition': {'severity': 'LOW',
                                           'id': '38b3c2b7-efe7',
                                           'name': 'Memory Usage'},
                      'id': 'ff43aacc-a5db-4f6f-a5d3-44f9cce8c714'},
                     {'state': 'ALARM',
                      'alarm_definition': {'severity': 'HIGH',
                                           'id': '38b3c2b7-efe8',
                                           'name': 'Latency Usage'},
                      'id': 'ff43aacc-a5db-4f6f-a5d3-44f9cce8c715'}
                     ]

ALARM_SHOW_OUTPUT = {'state': "ALARM",
                     'alarm_definition': {'severity': 'HIGH',
                                          'id': '38b3c2b7-efe8',
                                          'name': 'Latency Usage'},
                     'status': 'CRITICAL',
                     'id': 'ff43aacc-a5db-4f6f-a5d3-44f9cce8c715'
                     }


CALL_SERVICE_OUTPUT = {'ccp:cluster1':
                       ['standard-ccp-c1-m1-mgmt',
                        'standard-ccp-c1-m2-mgmt',
                        'standard-ccp-c1-m3-mgmt'],
                       'ccp:cluster2':
                       ['standard-ccp-c1-m1-mgmt',
                        'standard-ccp-c1-m2-mgmt',
                        'standard-ccp-c1-m3-mgmt']}

ALARM_COUNT_OUTPUT = {"counts":
                      [[5, "OK", "LOW"],
                       [6, "ALARM", "CRITICAL"],
                       [2, "ALARM", "HIGH"],
                       [3, "ALARM", "LOW"],
                       [7, "UNDETERMINED", "MED"]]}

METRIC_LIST_OUTPUT = [{"id": "0000f6b224259cf215505608edf6f10d7a3a273d",
                       "name": "swiftlm.systems.check_mounts",
                       "dimensions": {"cluster": "MyCluster",
                                      "hostname": "Myhostname",
                                      "service": "object-storage",
                                      "mount": "/dev/mqueue"}
                       }]


class Object_Storage_Data():
    def data_without_cluster_card(self):
        return {'end_time': '2016-08-28T23:41:15Z',
                'interval': '1',
                'period': '3600'}

    def data_without_cluster_graph(self):
        return {'end_time': '2016-08-28T23:41:15Z',
                'interval': '5',
                'period': '3600'}

    def data_with_cluster_card(self):
        return {'end_time': '2016-08-28T23:41:15Z',
                'interval': '1',
                'period': '3600',
                'cluster': 'MyCluster',
                'hostname': 'MyHostname'}

    def data_with_cluster_graph(self):
        return {'end_time': '2016-08-28T23:41:15Z',
                'interval': '5',
                'period': '3600',
                'cluster': 'MyCluster',
                'hostname': 'Myhostname'}

    def data_only_node(self):
        return {'cluster': 'MyCluster',
                'hostname': 'Myhostname'}


class TestObjectStorageSummarySvc(TestCase):
    def setUp(self):
        self.inst = Object_Storage_Data()

    def test_memory_card(self):
        data = self.inst.data_with_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(operation='memory',
                            data=data,
                            expected_output=expected_output)

    def test_storage_card(self):
        data = self.inst.data_with_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(operation='storage',
                            data=data,
                            expected_output=expected_output)

    def test_load_average_donut(self):
        data = self.inst.data_with_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(operation='load_average_donut',
                            data=data,
                            expected_output=expected_output)

    def test_time_to_replicate_card(self):
        data = self.inst.data_without_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(operation='time_to_replicate',
                            data=data,
                            expected_output=expected_output)

    def test_time_to_replicate_graph(self):
        data = self.inst.data_without_cluster_graph()
        expected_output = {'Swiftlm.Test': [['2016-08-27T23:41:15.000Z', 26.9],
                                            ['2016-07-28T07:41:15.000Z', 0.0],
                                            ['2016-07-28T11:41:15.000Z', 34.5],
                                            ['2016-07-28T19:41:15.000Z', 34.5],
                                            ['2016-08-28T22:41:15Z', -1],
                                            ['2016-08-28T23:41:15.000Z', 2.0]
                                            ]}
        self.common_handler(operation='time_to_replicate',
                            data=data,
                            expected_output=expected_output)

    def test_oldest_replication_completion_card(self):
        data = self.inst.data_without_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(
            operation='oldest_replication_completion',
            data=data,
            expected_output=expected_output)

    def test_oldest_replication_completion_graph(self):
        data = self.inst.data_without_cluster_graph()
        expected_output = {'Swiftlm.Test': [['2016-08-27T23:41:15.000Z', 26.9],
                                            ['2016-07-28T07:41:15.000Z', 0.0],
                                            ['2016-07-28T11:41:15.000Z', 34.5],
                                            ['2016-07-28T19:41:15.000Z', 34.5],
                                            ['2016-08-28T22:41:15Z', -1],
                                            ['2016-08-28T23:41:15.000Z', 2.0]
                                            ]}
        self.common_handler(
            operation='oldest_replication_completion',
            data=data,
            expected_output=expected_output)

    def test_current_capacity_card(self):
        data = self.inst.data_without_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(operation='current_capacity',
                            data=data,
                            expected_output=expected_output)

    def test_current_capacity_graph(self):
        data = self.inst.data_without_cluster_graph()
        expected_output = {'Swiftlm.Test':
                           [['2016-08-27T23:41:15.000Z', 26.9],
                            ['2016-07-28T07:41:15.000Z', 0.0],
                            ['2016-07-28T11:41:15.000Z', 34.5],
                            ['2016-07-28T19:41:15.000Z', 34.5],
                            ['2016-08-28T22:41:15Z', -1],
                            ['2016-08-28T23:41:15.000Z', 2.0]]}
        self.common_handler(operation='current_capacity',
                            data=data,
                            expected_output=expected_output)

    def test_filesystem_utilization_card(self):
        data = self.inst.data_with_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(operation='filesystem_utilization',
                            data=data,
                            expected_output=expected_output)

    def test_latency_healthcheck_card(self):
        data = self.inst.data_without_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(operation='latency_healthcheck',
                            data=data,
                            expected_output=expected_output)

    def test_latency_healthcheck_graph(self):
        data = self.inst.data_without_cluster_graph()
        expected_output = {'Swiftlm.Test': [['2016-08-27T23:41:15.000Z', 26.9],
                                            ['2016-07-28T07:41:15.000Z', 0.0],
                                            ['2016-07-28T11:41:15.000Z', 34.5],
                                            ['2016-07-28T19:41:15.000Z', 34.5],
                                            ['2016-08-28T22:41:15Z', -1],
                                            ['2016-08-28T23:41:15.000Z', 2.0]
                                            ]}
        self.common_handler(operation='latency_healthcheck',
                            data=data,
                            expected_output=expected_output)

    def test_latency_operational_card(self):
        data = self.inst.data_without_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(operation='latency_operational',
                            data=data,
                            expected_output=expected_output)

    def test_latency_operational_graph(self):
        data = self.inst.data_without_cluster_graph()
        expected_output = {'Swiftlm.Test': [['2016-08-27T23:41:15.000Z', 26.9],
                                            ['2016-07-28T07:41:15.000Z', 0.0],
                                            ['2016-07-28T11:41:15.000Z', 34.5],
                                            ['2016-07-28T19:41:15.000Z', 34.5],
                                            ['2016-08-28T22:41:15Z', -1],
                                            ['2016-08-28T23:41:15.000Z', 2.0]
                                            ]}
        self.common_handler(operation='latency_operational',
                            data=data,
                            expected_output=expected_output)

    def test_async_pending_card(self):
        data = self.inst.data_without_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(operation='async_pending',
                            data=data,
                            expected_output=expected_output)

    def test_async_pending_graph(self):
        data = self.inst.data_without_cluster_graph()
        expected_output = {'Swiftlm.Test': [['2016-08-27T23:41:15.000Z', 26.9],
                                            ['2016-07-28T07:41:15.000Z', 0.0],
                                            ['2016-07-28T11:41:15.000Z', 34.5],
                                            ['2016-07-28T19:41:15.000Z', 34.5],
                                            ['2016-08-28T22:41:15Z', -1],
                                            ['2016-08-28T23:41:15.000Z', 2.0]
                                            ]}
        self.common_handler(operation='async_pending',
                            data=data,
                            expected_output=expected_output)

    def test_alarms(self):
        data = self.inst.data_without_cluster_card()
        expected_output = {'counts': [[5, 'OK', 'LOW'],
                                      [6, 'ALARM', 'CRITICAL'],
                                      [2, 'ALARM', 'HIGH'],
                                      [3, 'ALARM', 'LOW'],
                                      [7, 'UNDETERMINED', 'MED']
                                      ]}
        self.common_handler(operation='alarms',
                            data=data,
                            expected_output=expected_output)

    def test_mount_status(self):
        data = self.inst.data_with_cluster_card()
        expected_output = {'total_mount_point': 1,
                           'mount_status': {'mounted': 0,
                                            'unmounted': 1}}
        self.common_handler(operation='mount_status',
                            data=data,
                            expected_output=expected_output)

    def test_service_availability_card(self):
        data = self.inst.data_without_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(operation='service_availability',
                            data=data,
                            expected_output=expected_output)

    def test_service_availability_graph(self):
        data = self.inst.data_without_cluster_graph()
        expected_output = {'Swiftlm.Test': [['2016-08-27T23:41:15.000Z', 26.9],
                                            ['2016-07-28T07:41:15.000Z', 0.0],
                                            ['2016-07-28T11:41:15.000Z', 34.5],
                                            ['2016-07-28T19:41:15.000Z', 34.5],
                                            ['2016-08-28T22:41:15Z', -1],
                                            ['2016-08-28T23:41:15.000Z', 2.0]
                                            ]}
        self.common_handler(operation='service_availability',
                            data=data,
                            expected_output=expected_output)

    def test_load_average_card(self):
        data = self.inst.data_without_cluster_card()
        expected_output = {'Swiftlm.Test': 2.0}
        self.common_handler(operation='load_average',
                            data=data,
                            expected_output=expected_output)

    def test_load_avaergae_graph(self):
        data = self.inst.data_without_cluster_graph()
        expected_output = {'Swiftlm.Test': [['2016-08-27T23:41:15.000Z', 26.9],
                                            ['2016-07-28T07:41:15.000Z', 0.0],
                                            ['2016-07-28T11:41:15.000Z', 34.5],
                                            ['2016-07-28T19:41:15.000Z', 34.5],
                                            ['2016-08-28T22:41:15Z', -1],
                                            ['2016-08-28T23:41:15.000Z', 2.0]
                                            ]}
        self.common_handler(operation='load_average',
                            data=data,
                            expected_output=expected_output)

    def test_file_systems(self):
        data = self.inst.data_with_cluster_card()
        expected_output = {'/dev/mqueue': {'Swiftlm.Test': 2.0}}
        self.common_handler(operation='file_systems',
                            data=data,
                            expected_output=expected_output)

    def test_rate_of_change_card(self):
        data = self.inst.data_with_cluster_card()
        expected_output = [-32.5]
        self.common_handler(operation='rate_of_change',
                            data=data,
                            expected_output=expected_output)

    def test_rate_of_change_graph(self):
        data = self.inst.data_with_cluster_graph()
        expected_output = [['2016-08-27T23:41:15.000Z', -26],
                           ['2016-07-28T07:41:15.000Z', 34],
                           ['2016-07-28T11:41:15.000Z', 0],
                           ['2016-07-28T19:41:15.000Z', -32],
                           ['2016-08-28T22:41:15Z', -1],
                           ['2016-08-28T23:41:15Z', -1]]
        self.common_handler(operation='rate_of_change',
                            data=data,
                            expected_output=expected_output)

    def test_heat_map_cpu_load_average(self):
        data = self.inst.data_without_cluster_card()
        self.common_handler(operation='heat_map_cpu_load_average',
                            data=data,
                            expected_output=[])

    def test_alarm_description(self):
        data = self.inst.data_with_cluster_card()
        expected_output = {'ff43aacc-a5db-4f6f-a5d3-44f9cce8c713':
                           {'status': 'CRITICAL',
                            'state': 'ALARM',
                            'description': 'Alarms',
                            'alarm_definition_id': '38b3c2b7-efe8',
                            'name': 'Latency Usage',
                            'severity': 'HIGH'},
                           'ff43aacc-a5db-4f6f-a5d3-44f9cce8c715':
                           {'status': 'CRITICAL',
                            'state': 'ALARM',
                            'description': 'Alarms',
                            'alarm_definition_id': '38b3c2b7-efe8',
                            'name': 'Latency Usage',
                            'severity': 'HIGH'},
                           'ff43aacc-a5db-4f6f-a5d3-44f9cce8c714':
                           {'status': 'CRITICAL',
                            'state': 'ALARM',
                            'description': 'Alarms',
                            'alarm_definition_id': '38b3c2b7-efe8',
                            'name': 'Latency Usage',
                            'severity': 'HIGH'}}
        self.common_handler(operation='alarm_description', data=data,
                            expected_output=expected_output)

    def test_heat_map_utilization_focused_inventory(self):
        data = self.inst.data_without_cluster_card()
        self.common_handler(
            operation='heat_map_utilization_focused_inventory',
            data=data, expected_output=[])

    @patch.object(AlarmsManager, 'count')
    @patch.object(objectstorage_summary_service.ObjectStorageSummarySvc,
                  'call_service')
    @patch.object(TokenHelpers, 'get_service_endpoint')
    @patch.object(TokenHelpers, 'get_token_for_project')
    def test_node_state(self, mock_get_token_for_project,
                        mock_get_service_endpoint,
                        mock_call_service,
                        mock_alarm_count):
        mock_get_token_for_project.return_value = "admin"
        mock_get_service_endpoint.return_value = "http://localhost:8070/v2.0"
        mock_call_service.return_value = {'ccp:cluster1':
                                          ['standard-ccp-c1-m1-mgmt',
                                           'standard-ccp-c1-m2-mgmt',
                                           'standard-ccp-c1-m3-mgmt'],
                                          'ccp:cluster2':
                                          ['standard-ccp-c1-m1-mgmt',
                                           'standard-ccp-c1-m2-mgmt',
                                           'standard-ccp-c1-m3-mgmt']}
        mock_alarm_count.return_value = {"counts":
                                         [[5, "OK", "LOW"],
                                          [6, "ALARM", "CRITICAL"],
                                          [2, "ALARM", "HIGH"],
                                          [3, "ALARM", "LOW"],
                                          [7, "UNDETERMINED", "MED"]]}
        request = {
            api.TARGET: 'objectstorage_summary_service',
            api.ACTION: 'GET',
            api.AUTH_TOKEN: 'unused',
            api.DATA: {
                api.OPERATION: "node_state",
                api.DATA: None
                }
            }
        svc = objectstorage_summary_service.ObjectStorageSummarySvc(
            bll_request=BllRequest(request))
        reply = svc.handle()
        self.assertEqual(reply['status'], api.STATUS_INPROGRESS)

    @patch.object(AlarmsManager, 'count')
    @patch.object(objectstorage_summary_service.ObjectStorageSummarySvc,
                  'call_service')
    @patch.object(TokenHelpers, 'get_service_endpoint')
    @patch.object(TokenHelpers, 'get_token_for_project')
    def test_health_focused(self, mock_get_token_for_project,
                            mock_get_service_endpoint,
                            mock_call_service,
                            mock_alarm_count):
        mock_get_token_for_project.return_value = "admin"
        mock_get_service_endpoint.return_value = "http://localhost:8070/v2.0"
        mock_call_service.return_value = {'ccp:cluster1':
                                          ['standard-ccp-c1-m1-mgmt',
                                           'standard-ccp-c1-m2-mgmt',
                                           'standard-ccp-c1-m3-mgmt'],
                                          'ccp:cluster2':
                                          ['standard-ccp-c1-m1-mgmt',
                                           'standard-ccp-c1-m2-mgmt',
                                           'standard-ccp-c1-m3-mgmt']}
        mock_alarm_count.return_value = {"counts": [[5, "OK", "LOW"],
                                                    [6, "OK", "HIGH"]]}
        request = {
            api.TARGET: 'objectstorage_summary_service',
            api.ACTION: 'GET',
            api.AUTH_TOKEN: 'unused',
            api.DATA: {
                api.OPERATION: "health_focused",
                api.DATA: None
                }
            }
        svc = objectstorage_summary_service.ObjectStorageSummarySvc(
            bll_request=BllRequest(request))
        reply = svc.handle()
        self.assertEqual(reply['status'], api.STATUS_INPROGRESS)

    @patch.object(objectstorage_summary_service.ObjectStorageSummarySvc,
                  'call_service')
    @patch.object(AlarmsManager, 'list')
    @patch.object(AlarmsManager, 'get')
    @patch.object(AlarmDefinitionsManager, 'get')
    @patch.object(AlarmsManager, 'count')
    @patch.object(MetricsManager, 'list')
    @patch.object(MetricsManager, 'list_statistics')
    @patch.object(MetricsManager, 'list_measurements')
    @patch.object(TokenHelpers, 'get_service_endpoint')
    @patch.object(TokenHelpers, 'get_token_for_project')
    def common_handler(self, mock_get_token_for_project,
                       mock_get_service_endpoint,
                       mock_get_measurement_list,
                       mock_get_statistics_list,
                       mock_get_list,
                       mock_get_alarm_count,
                       mock_get_alarm_definition_get,
                       mock_get_alarm_get,
                       mock_get_alarm_list,
                       mock_call_service,
                       operation, data, expected_output):
        mock_get_token_for_project.return_value = "admin"
        mock_get_service_endpoint.return_value = "http://localhost:8070/v2.0"
        mock_get_measurement_list.return_value = MEASUREMENT_OUPUT
        mock_get_statistics_list.return_value = STATISTICS_OUTPUT
        mock_get_list.return_value = METRIC_LIST_OUTPUT
        mock_get_alarm_count.return_value = ALARM_COUNT_OUTPUT
        mock_get_alarm_definition_get.return_value = \
            ALARM_DEFINITION_SHOW_OUTPUT
        mock_get_alarm_get.return_value = ALARM_SHOW_OUTPUT
        mock_get_alarm_list.return_value = ALARM_LIST_OUTPUT
        mock_call_service.return_value = CALL_SERVICE_OUTPUT
        request = {
            api.TARGET: 'objectstorage_summary_service',
            api.ACTION: 'GET',
            api.AUTH_TOKEN: 'unused',
            api.DATA: {
                api.OPERATION: operation,
                api.DATA: data
                }
            }
        svc = objectstorage_summary_service.ObjectStorageSummarySvc(
            bll_request=BllRequest(request))
        reply = svc.handle()
        expected = expected_output
        self.assertEqual(reply[api.DATA], expected)

    def test_project_capacity_metric_card_selected_project(self):
        data = {"end_time": "2016-07-15T23:00:00Z",
                "interval": 1,
                "period": 3600,
                "id": "123"}
        operation = "project_capacity"
        self.project_common_handler(operation=operation, data=data)

    def test_project_capacity_metric_card_all_project(self):
        data = {"end_time": "2016-07-15T23:00:00Z",
                "interval": 1,
                "period": 3600,
                "id": "all"}
        operation = "project_capacity"
        self.project_common_handler(operation=operation, data=data)

    def test_project_capacity_time_series_all_project(self):
        data = {"end_time": "2016-07-15T23:00:00Z",
                "interval": 24,
                "period": 3600,
                "id": "all"}
        operation = "project_capacity"
        self.project_common_handler(operation=operation, data=data)

    def test_project_capacity_time_series_selected_project(self):
        data = {"end_time": "2016-07-15T23:00:00Z",
                "interval": 24,
                "period": 3600,
                "id": "123"}
        operation = "project_capacity"
        self.project_common_handler(operation=operation, data=data)

    def test_project_capacity_roc_metric_card_selected_project(self):
        data = {"end_time": "2016-07-15T23:00:00Z",
                "interval": 2,
                "period": 3600,
                "id": "123"}
        operation = "project_capacity_roc"
        self.project_common_handler(operation=operation, data=data)

    def test_project_capacity_roc_metric_card_all_project(self):
        data = {"end_time": "2016-07-15T23:00:00Z",
                "interval": 2,
                "period": 3600,
                "id": "all"}
        operation = "project_capacity_roc"
        self.project_common_handler(operation=operation, data=data)

    def test_project_capacity_roc_time_series_all_project(self):
        data = {"end_time": "2016-07-15T23:00:00Z",
                "interval": 24,
                "period": 3600,
                "id": "all"}
        operation = "project_capacity_roc"
        self.project_common_handler(operation=operation, data=data)

    def test_project_capacity_roc_time_series_selected_project(self):
        data = {"end_time": "2016-07-15T23:00:00Z",
                "interval": 24,
                "period": 3600,
                "id": "123"}
        operation = "project_capacity_roc"
        self.project_common_handler(operation=operation, data=data)

    def test_topten_project_capacity(self):
        data = {"end_time": "2016-07-15T23:00:00Z",
                "interval": 6,
                "period": 3600}
        operation = "topten_project_capacity"
        self.project_common_handler(operation=operation, data=data)

    @patch.object(MetricsManager, 'list_statistics')
    @patch.object(objectstorage_summary_service.ObjectStorageSummarySvc,
                  'call_service')
    @patch.object(TokenHelpers, 'get_service_endpoint')
    @patch.object(TokenHelpers, 'get_token_for_project')
    def project_common_handler(self, mock_get_token_for_project,
                               mock_get_service_endpoint,
                               mock_call_service,
                               mock_list_statistics,
                               operation, data):
        mock_get_token_for_project.return_value = "admin"
        mock_get_service_endpoint.return_value = "http://localhost:8070/v2.0"
        mock_call_service.return_value = [
            {"id": "34c037934d852ea7", "name": "backup"},
            {"id": "2e3a733b4559c20f", "name": "demo"}
        ]
        mock_list_statistics.return_value = [
            {"dimensions": {"user_id": "None",
                            "cloud_name": "standard",
                            "region": "None",
                            "resource_id": "62d256ae5f1748dab8fedf8ebdf4b802",
                            "control_plane": "ccp",
                            "cluster": "cluster1",
                            "datasource": "ceilometer",
                            "project_id": "62d256ae5f1748dab8fedf8ebdf4b802",
                            "type": "gauge",
                            "unit": "B",
                            "source": "openstack"},
             "statistics": [["2016-07-15T23:00:00.000Z", 300],
                            ["2016-07-16T00:00:00.000Z", 450],
                            ["2016-07-16T01:00:00.000Z", 250],
                            ["2016-07-16T02:00:00.000Z", 500],
                            ["2016-07-16T03:00:00.000Z", 600]
                            ]
             }]
        request = {
            api.TARGET: 'objectstorage_summary_service',
            api.ACTION: 'GET',
            api.AUTH_TOKEN: 'unused',
            api.DATA: {
                api.OPERATION: operation,
                api.DATA: data,
            }
        }
        svc = objectstorage_summary_service.ObjectStorageSummarySvc(
            bll_request=BllRequest(request))
        reply = svc.handle()
        self.assertEqual(reply['status'], api.STATUS_INPROGRESS)
