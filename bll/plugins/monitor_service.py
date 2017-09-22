# (c) Copyright 2015-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

import logging

from datetime import datetime, timedelta
from monascaclient import client as msclient
from collections import defaultdict

from bll import api
from bll.common.util import get_conf
from bll.plugins.service import SvcBase, expose
from bll.common.exception import InvalidBllRequestException

TYPE_UNKNOWN = 'unknown'
TYPE_UP = 'up'
TYPE_DOWN = 'down'

LOG = logging.getLogger(__name__)

api_version = '2_0'


class MonitorSvc(SvcBase):
    """
    Obtain monitoring information from monasca.

    The ``target`` value for this plugin is ``monitor``. See :ref:`rest-api`
    for a full description of the request and response formats.
    """

    # The monasca alarm definition update only permits these keys to be
    # supplied
    UPDATEABLE_KEYS = (
        'alarm_id',
        'undetermined_actions',
        'name',
        'alarm_actions',
        'match_by',
        'expression',
        'ok_actions',
        'description',
        'severity',
        'actions_enabled')

    def __init__(self, *args, **kwargs):
        """
        Set default values for service.
        """
        super(MonitorSvc, self).__init__(*args, **kwargs)
        self.client = self._get_monasca_client()

    def _get_monasca_client(self):
        """
        Build the monasca client
        """

        monasca_url = self.token_helper.get_service_endpoint('monitoring')
        # All monasca data is stored in the admin project, so get a token
        # to that project
        token = self.token_helper.get_token_for_project('admin')

        return msclient.Client(api_version,
                               monasca_url,
                               token=token,
                               insecure=get_conf("insecure"),
                               user_agent=api.USER_AGENT)

    def _get_alarm_data(self):
        """
        Helper function to extract the fields relevant for alarms and replace
        'id' with 'alarm_id'
        :return:
        """
        return self._replace_id(self.request.get_data(), 'alarm_id')

    def _get_notif_data(self):
        """
        Helper function to extract the fields relevant for notifications and
        replace 'id' with 'notification_id'
        :return:
        """
        return self._replace_id(self.request.get_data(), 'notification_id')

    @expose()
    def alarm_definition_create(self):
        return self.client.alarm_definitions.create(**self._get_alarm_data())

    @expose()
    def alarm_definition_delete(self):
        self.client.alarm_definitions.delete(**self._get_alarm_data())

    @expose()
    def alarm_definition_list(self):
        return self.client.alarm_definitions.list(**self._get_alarm_data())

    @expose()
    def alarm_definition_patch(self):
        return self.client.alarm_definitions.patch(**self._get_alarm_data())

    @expose()
    def alarm_definition_show(self):
        return self.client.alarm_definitions.get(**self._get_alarm_data())

    @expose()
    def alarm_definition_update(self):
        # Monasca complains if the several of the values returned from
        # the show are fed back into the update
        data = self._get_alarm_data()
        updated_values = {k: v for k, v in data.iteritems()
                          if k in self.UPDATEABLE_KEYS}
        return self.client.alarm_definitions.update(**updated_values)

    @expose()
    def alarm_delete(self):
        self.client.alarms.delete(**self._get_alarm_data())

    @expose()
    def alarm_history(self):
        return self.client.alarms.history(**self._get_alarm_data())

    @expose()
    def alarm_history_list(self):
        return self.client.alarms.history_list(**self._get_alarm_data())

    @expose()
    def alarm_list(self):
        return self.client.alarms.list(**self._get_alarm_data())

    @expose()
    def alarm_patch(self):
        return self.client.alarms.patch(**self._get_alarm_data())

    @expose()
    def alarm_show(self):
        return self.client.alarms.get(**self._get_alarm_data())

    @expose()
    def alarm_update(self):
        data = self._get_alarm_data()
        # Monasca complains if some fields from the show
        # are fed back into the update
        for key in ('links',
                    'alarm_definition',
                    'metrics',
                    'created_timestamp',
                    'updated_timestamp',
                    'state_updated_timestamp'):
            if key in data:
                data.pop(key)
        return self.client.alarms.update(**data)

    @expose()
    def measurement_list(self):
        return self.client.metrics.list_measurements(**self.request.get_data())

    @expose()
    def metric_create(self):
        return self.client.metrics.create(**self.request.get_data())

    @expose()
    def metric_list(self):
        return self.client.metrics.list(**self.request.get_data())

    @expose()
    def metric_names(self):
        return self.client.metrics.list_names(**self.request.get_data())

    @expose()
    def metric_statistics(self):
        return self.client.metrics.list_statistics(**self.request.get_data())

    @expose()
    def notification_create(self):
        return self.client.notifications.create(**self._get_notif_data())

    @expose()
    def notification_delete(self):
        self.client.notifications.delete(**self._get_notif_data())

    @expose()
    def notification_list(self):
        return self.client.notifications.list(**self._get_notif_data())

    @expose()
    def notification_show(self):
        return self.client.notifications.get(**self._get_notif_data())

    @expose()
    def notification_update(self):
        data = self._get_notif_data()
        # Monasca complains if the links returned from the show
        # are fed back into the update
        data.pop('links', None)

        return self.client.notifications.update(**data)

    @expose()
    def notificationtype_list(self):
        return self.client.notificationtypes.list(**self.request.get_data())

    @expose()
    def get_all_instances_status(self):
        results = {}

        for name in ['vm.host_alive_status', 'vm.ping_status']:
            parms = {}
            parms['name'] = name
            parms['start_time'] = \
                (datetime.utcnow() - timedelta(minutes=5)).isoformat()
            parms['group_by'] = '*'
            parms['dimensions'] = {'component': 'vm'}
            meas_groups = self.client.metrics.list_measurements(**parms)
            for meas_info in meas_groups:
                key = meas_info['dimensions']['resource_id']
                if key not in results:
                    results[key] = {}
                try:
                    meas = meas_info['measurements']
                    (time, code, value) = meas[-1]
                    results[key][name] = int(code)
                    # Special-case handling for value_meta_data
                    # from host_alive_status
                    if name == 'vm.host_alive_status':
                        results[key]['host_alive_status_value_meta_detail'] = \
                            value.get('detail', '')
                except (IndexError, TypeError, KeyError):
                    # Something really bad happened if there are
                    # no measurements
                    results[key][name] = -1

        return results

    @expose()
    def get_instance_metrics(self):

        data = self.request.get_data()
        results = {}
        if 'instances' not in data or 'metrics' not in data:
            # you give me nothing, I give you nothing
            return results

        # NOTE: We get the last 5 minutes of data and calc an average
        #       for the request metrics.  This avoids issues where we
        #       may not receive measurement data for some reason within
        #       the last second or minute or xxx.
        for instance in data['instances']:
            instdata = {}
            for metric in data['metrics']:
                instdata[metric] = self._get_5min_avg_metric(instance, metric)
            results[instance] = instdata
        return results

    def _get_5min_avg_metric(self, instance, metric):
        parms = {}
        parms["dimensions"] = {"resource_id": instance}
        parms["name"] = metric
        parms["merge_metrics"] = True
        try:
            # get 5 minutes of measurement data
            parms["start_time"] = \
                (datetime.utcnow() - timedelta(minutes=5)).isoformat()
            measurements = self.client.metrics.list_measurements(**parms)
            values = measurements[0]['measurements']

            # and calculate the mean for this data
            return sum(secs for secs in (i[1] for i in values)) / len(values)
        except:
            # If we couldn't get any data or div by zero or whatever
            # mark this data as unknown since we couldn't get it
            # The UI will see this value as 'null'
            return None

    def _replace_id(self, data, field):
        """
        The monasca API does not follow the REST standard: the data returned
        from GETs always has an id field named 'id', but the data expected in
        PUT, DELETE, and PATCH expects the id field to be named something else:
        sometimes alarm_id or notification_id.  This function can be used to
        adjust the incoming data to match what the API function expects
        """
        if 'id' not in data:
            return data

        result = data.copy()
        id = result.pop('id')

        if field not in result:
            result[field] = id

        return result

    def _get_host_measurements(self, observer, hostname, status_data):
        if not status_data:
            return []

        for status in status_data:
            host = status['dimensions']['hostname']
            obs = status['dimensions']['observer_host']
            if host == hostname and obs == observer:
                return status

        return []

    @expose('get_appliances_status')
    def get_appliances_status(self):

        data = self.request.get_data()
        results = {}
        if 'hostnames' not in data:
            return results

        # get ALL the ping measurements for all hosts
        start_time = (datetime.utcnow() - timedelta(minutes=5)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        meas_parms = {
            'name': 'host_alive_status',
            "start_time": start_time,
            'group_by': "*",
            'dimensions': {
                'test_type': 'ping'
            }
        }
        ping_measurements = self.client.metrics.list_measurements(**meas_parms)

        target_hosts = defaultdict(set)
        all_observers = set()
        for meas in ping_measurements:
            hostname = meas['dimensions']['hostname']
            observer = meas['dimensions']['observer_host']
            target_hosts[hostname].add(observer)
            all_observers.add(observer)

        # for each target host, see if it's pingable by any of the observers
        for hostname in data['hostnames']:
            # requesting status for a non-existent target host
            if hostname not in target_hosts:
                if hostname in all_observers:
                    # This host is an observer(ping source), therefore, if it
                    # can ping other target hosts, then we presume it is up
                    for meas in ping_measurements:
                        observer = meas['dimensions']['observer_host']
                        if hostname == observer:
                            if self._get_ping_status(meas) == TYPE_UP:
                                # found at least one target host with a good
                                # ping so stop looking and mark the observer
                                # host as good
                                results[hostname] = TYPE_UP
                                break

                    # if we couldn't find a good ping,
                    if not results.get(hostname):
                        results[hostname] = TYPE_UNKNOWN
                else:
                    # This host is not a ping source or target
                    results[hostname] = TYPE_UNKNOWN
            else:
                # requesting status for an existing target host
                final_ping_status = TYPE_UNKNOWN
                for observer in target_hosts[hostname]:
                    meas = self._get_host_measurements(
                        observer, hostname, ping_measurements)
                    ping_status = self._get_ping_status(meas)

                    # if it's up, we stop checking and say it's up.
                    if ping_status == TYPE_UP:
                        final_ping_status = TYPE_UP
                        break
                    # if it's down, we say it's down, but keep looking.
                    if ping_status == TYPE_DOWN:
                        final_ping_status = TYPE_DOWN
                    # We ignore TYPE_UNKNOWNs unless they're all TYPE_UNKNOWNs.
                results[hostname] = final_ping_status
        return results

    def _get_ping_status(self, host_meas):
        if not host_meas or not host_meas['measurements']:
            return TYPE_UNKNOWN
        (time, ping_value, value_meta) = host_meas['measurements'][-1]
        if ping_value == 0.0:
            return TYPE_UP
        elif ping_value == 1.0:
            return TYPE_DOWN
        else:
            return TYPE_UNKNOWN

    @expose('alarm_count')
    def _get_alarm_count(self):

        data = self.request.get_data()

        # Was there a dimension_name_filter given?
        dim_name_filter_str = data.pop('dimension_name_filter', None)
        if dim_name_filter_str:
            dim_name_filters = [str.strip()
                                for str in dim_name_filter_str.split(',')]
            # make sure dimension dimension_name is in group_by
            if 'group_by' not in data.keys() \
                    or 'dimension_name' not in data['group_by']:
                raise InvalidBllRequestException(self._(
                    'cannot filter on dimension_name_filter: {} '
                    'without a group_by on dimension_name').format(
                        dim_name_filter_str))
        else:
            dim_name_filters = None

        # Monasca has a 10K limit from alarm-count and we want all of them, so
        # page thru all of them
        limit = 10000
        offset = 0
        all_counts = []
        while True:
            data['limit'] = limit
            data['offset'] = offset
            alarm_counts = self.client.alarms.count(**data)
            columns = alarm_counts['columns']
            counts = alarm_counts['counts']

            # Handle the situation where we hit a page boundary (i.e. have no
            # more items at all
            # This happens when the next page returns something like
            # counts = [[0, None, None, .....] where the first entry is
            # 0 and subsequent elements are all 'None'
            if len(counts) == 1 and \
                len(counts[0]) > 1 and \
                counts[0][1] is None:
                break

            all_counts.extend(counts)
            if len(counts) < limit:
                # we got it all, so no need to get any more
                break
            offset += limit

        # Do we need to do any filtering?
        if dim_name_filters:
            dim_idx = columns.index('dimension_name')
            filtered_counts = [c for c in all_counts if c[dim_idx]
                               in dim_name_filters]
            all_counts = filtered_counts

        return {
            'columns': columns,
            'counts': all_counts
        }

    @classmethod
    def needs_services(cls):
        return ['monitoring']
