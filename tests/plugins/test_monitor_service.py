# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from datetime import timedelta, datetime
import unittest
from mock import patch, MagicMock

from monascaclient import client as msclient
from tests.util import functional, get_token_from_env, TestCase, \
    create_user, delete_user
from bll.api.request import BllRequest, InvalidBllRequestException
from bll import api
from bll.plugins.monitor_service import TYPE_UNKNOWN, TYPE_UP, \
    MonitorSvc


@functional('keystone,monasca')
class TestMonitorSvc(TestCase):

    def setUp(self):
        self.user = None
        self.alarm_definition_id = None
        self.notification_id = None
        self.token = get_token_from_env()

        self.mock_moncli = MagicMock(spec=msclient.Client)

    def tearDown(self):
        if self.alarm_definition_id:
            self.monitor_operation('alarm_definition_delete',
                                   dict(id=self.alarm_definition_id))
        if self.notification_id:
            self.monitor_operation('notification_delete',
                                   dict(id=self.notification_id))

        if self.user:
            delete_user(self.user)

    def monitor_operation(self, operation, data=None):
        """
        Call the monitor service to perform the given operation, without
        any assertions.  The lack of assertions is useful in scenarios where
        success it not expected and/or required
        """

        request = {
            api.TARGET: 'monitor',
            api.AUTH_TOKEN: self.token,
            api.DATA: {
                api.OPERATION: operation,
                api.VERSION: 'v1',
            }
        }
        if data:
            request[api.DATA].update(data)

        svc = MonitorSvc(bll_request=BllRequest(request))
        return svc.handle()

    def monitor(self, operation, data=None):
        """
        Performs a monitor operation, and asserts for success
        """

        reply = self.monitor_operation(operation, data)
        self.assertEqual(api.COMPLETE, reply[api.STATUS])
        self.assertIn(api.PROGRESS, reply)
        self.assertIn(api.STARTTIME, reply)
        return reply[api.DATA]

    def test_alarm_count_all(self):
        output = self.monitor('alarm_count')
        self.assertIsNotNone(output)
        self.assertIn('counts', output)
        self.assertIn('columns', output)
        total_alarms = output['counts'][0][0]

        # There is almost always some sort of alarm
        self.assertNotEqual(total_alarms, 0)

        parms = {'group_by': "severity,state"}
        output = self.monitor('alarm_count', parms)

        # Flatten the array of arrays and look for any valid
        vals = [val for innerlist in output['counts'] for val in innerlist]

        # There should be a valid severity in there somewhere
        self.assertTrue(any(val in vals for val in ['LOW', 'MEDIUM', 'HIGH']))

        # There should be a valid state in there somewhere
        self.assertTrue(any(val in vals for val in ['UNDETERMINED', 'OK',
                                                    'ALARM']))

    def test_alarm_count_filter(self):
        # We want only counts where dimension_name = service or hostname
        parms = {
            'dimension_name_filter': 'service,hostname',
            'group_by': 'dimension_name,dimension_value,severity,state'
        }
        output = self.monitor('alarm_count', parms)

        dim_idx = output['columns'].index('dimension_name')
        for count in output['counts']:
            self.assertTrue(count[dim_idx] in ('service', 'hostname'))

        # But what happens if we specify the dimension_name_filter without
        # specifying dimension_name in the group_by
        parms = {
            'dimension_name_filter': 'service,hostname',
            'group_by': 'severity,state'
        }

        with self.assertRaises(InvalidBllRequestException):
            self.monitor('alarm_count', parms)

    def test_alarm_definitions(self):

        name = "TEST alarm -- delete me"
        definition_data = {
            "name": name,
            "description": "TEST -- delete me",
            "expression": "disk.space_used_perc>90",
            "match_by": ["hostname"],
            "severity": "LOW"
        }

        data = self.monitor('alarm_definition_create', definition_data)
        self.assertIn('id', data)
        id = data['id']

        # Enable tearDown to cleanup in case of subsequent failures
        self.alarm_definition_id = id

        data = self.monitor('alarm_definition_list')
        self.assertIn(id, [dfn['id'] for dfn in data])

        data = self.monitor('alarm_definition_show', dict(id=id))
        self.assertEquals(id, data.get('id'))
        self.assertEquals(name, data.get('name'))

        desc = 'Updated description'
        data['description'] = desc
        data = self.monitor('alarm_definition_update', data)
        self.assertEquals(desc, data.get('description'))

        desc = 'Patched description'
        data = self.monitor('alarm_definition_patch',
                            dict(id=id, description=desc))

        data = self.monitor('alarm_definition_show', dict(id=id))
        self.assertEquals(id, data.get('id'))
        self.assertEquals(desc, data.get('description'))

        # clean up
        self.monitor('alarm_definition_delete', dict(id=id))

        self.alarm_definition_id = None

    def test_notifications(self):

        name = "TEST -- delete"
        definition_data = {
            "name": name,
            "type": "EMAIL",
            "address": "foo@bar.com"
        }

        data = self.monitor('notification_create', definition_data)
        self.assertIn('id', data)
        id = data['id']

        # Enable tearDown to cleanup in case of subsequent failures
        self.notification_id = id

        data = self.monitor('notification_list')
        self.assertIn(id, [dfn['id'] for dfn in data])

        data = self.monitor('notification_show', dict(id=id))
        self.assertEquals(id, data.get('id'))
        self.assertEquals(name, data.get('name'))

        address = 'updated@bar.com'
        data['address'] = address
        data = self.monitor('notification_update', data)
        self.assertEquals(address, data.get('address'))

        # clean up
        self.monitor('notification_delete', dict(id=id))

        self.notification_id = None

        data = self.monitor('notificationtype_list')
        self.assertIn('EMAIL', [datum['type'] for datum in data])
        self.assertIn('WEBHOOK', [datum['type'] for datum in data])
        self.assertIn('PAGERDUTY', [datum['type'] for datum in data])

    def test_metrics(self):

        # NOTE - since there is no API for deleting a metric, this test will
        # not exercise the metric_create API and pollute the system with test
        # data

        data = self.monitor('metric_list')
        self.assertGreater(len(data), 1)

        # Grab the first metric from the list
        name = data[0]['name']
        dimensions = data[0]['dimensions']
        end_time = datetime.utcnow()
        start_time = end_time + timedelta(-1)

        # Exercise metric_statistics
        data = self.monitor('metric_statistics', {
            'name': name,
            'statistics': 'avg',
            'dimensions': dimensions,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat()
        })
        self.assertGreater(len(data[0]['statistics']), 1)

        # Exercise measurement-list
        data = self.monitor('measurement_list', {
            'name': name,
            'dimensions': dimensions,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat()
        })
        self.assertGreater(len(data[0]['measurements']), 1)

    @unittest.skip("skipping test_alarms() due to JAH-2347")
    def test_alarms(self):

        # NOTE - since there is no API for creating an alarm, this test will
        # not exercise the alarm_delete API

        data = self.monitor('alarm_list')
        self.assertGreater(len(data), 1)

        # Grab the first alarm from the list
        id = data[0]['id']

        data = self.monitor('alarm_show', dict(id=id))
        self.assertEquals(id, data.get('id'))

        old_lifecycle_state = data['lifecycle_state']

        new_lifecycle_state = 'foo'
        data['lifecycle_state'] = new_lifecycle_state
        data = self.monitor('alarm_update', data)
        self.assertEquals(new_lifecycle_state, data.get('lifecycle_state'))

        # Now put it back where it started, using patch
        data = self.monitor('alarm_patch',
                            dict(id=id, lifecycle_state=old_lifecycle_state))
        data = self.monitor('alarm_show', dict(id=id))
        self.assertEquals(old_lifecycle_state, data.get('lifecycle_state'))

        # Verify that alarm history succeeds
        self.monitor('alarm_history', dict(id=id))

        # Verify that alarm history list succeeds
        end_time = datetime.utcnow()
        start_time = end_time + timedelta(-1)
        self.monitor('alarm_history_list', {
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat()
        })

    def test_monasca_user_role(self):
        # Test that a user with monasca-user role can retrieve monasca data
        (self.user, password) = create_user({'admin': 'monasca-user',
                                             'demo': 'admin'},
                                            {'Default': 'admin'})

        data = self.monitor('notification_list')
        self.assertGreater(len(data), 0)

    def mock_cli_get_all_instances_status(start_time, group_by, dimensions,
                                          name):
        meas_groups = []
        for i in range(3):
            host = {}
            host['dimensions'] = {}
            host['dimensions']['hostname'] = "host%s" % i
            host['dimensions']['resource_id'] = "host%s_id" % i
            host['measurements'] = [['time1', 0.0, {}]]
            meas_groups.append(host)
        return meas_groups

    @patch('monascaclient.v2_0.metrics.MetricsManager.list_measurements',
           side_effect=mock_cli_get_all_instances_status)
    def test_get_all_instances_status(self, mockname):
        # functional test

        data = self.monitor('get_all_instances_status')
        self.assertEqual(len(data), 3)  # there are 3 hosts
        for i in range(len(data)):     # for each host, verify good status
            self.assertEqual(data["host%d_id" % i]['vm.host_alive_status'], 0)
            self.assertEqual(data["host%d_id" % i]['vm.ping_status'], 0)
            self.assertEqual(data["host%d_id" % i]
                             ['host_alive_status_value_meta_detail'], '')

    def test_get_appliances_status(self):

        # bad hosts
        data = self.monitor('get_appliances_status', data={
            'hostnames': ['moe', 'larry', 'curly']
        })
        for status in data.values():
            self.assertEquals(status, TYPE_UNKNOWN)

        # see if we can come up with a list of good hosts
        metrics_list = self.monitor('metric_list', data={
            'name': 'host_alive_status',
        })

        # this won't work if the whole cloud is in one host, but since we
        # never do that in our functional tests
        hostnames = []
        for metric in metrics_list:
            hostname = metric['dimensions']['hostname']
            if hostname not in hostnames:
                hostnames.append(hostname)

        # we expect all these hosts to be up.  If not, our cloud is falling
        # apart and should be rebuilt.
        data = self.monitor('get_appliances_status', data={
            'hostnames': hostnames
        })
        for status in data.values():
            self.assertIn(status, (TYPE_UP, TYPE_UNKNOWN))
            if status == TYPE_UNKNOWN:
                print "Perhaps it's time to rebuild the cloud??"
