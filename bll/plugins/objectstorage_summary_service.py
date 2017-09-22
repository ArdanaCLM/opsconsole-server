# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from builtins import range
import logging
import copy
from datetime import datetime, timedelta
from monascaclient import client
from bll import api
from bll.common.util import get_conf
from bll.plugins.service import SvcBase, expose

LOG = logging.getLogger(__name__)
api_version = '2_0'


class ObjectStorageSummarySvc(SvcBase):

    """
    Retrieve summaries of Object Storage monitoring data.

    The ``target`` value for this plugin is ``objectstorage_summary``. See
    :ref:`rest-api` for a full description of the request and response formats.

    The services in this file are all specific queries to monasca and have
    peculiar response formats that are tightly coupled with the UI screens
    that call them.

    All time values should be specified in UTC and should follow the ISO-8601
    date/time format, for example: 2016-12-25T00:00:00Z .
    """
    def __init__(self, *args, **kwargs):
        super(ObjectStorageSummarySvc, self).__init__(*args, **kwargs)

        self.monasca_client = self._get_monasca_client()

    def _get_monasca_client(self):
        """
        Build the monasca client
        """

        monasca_url = self.token_helper.get_service_endpoint('monitoring')
        # All monasca data is stored in the admin project, so get a token
        # to that project
        token = self.token_helper.get_token_for_project('admin')

        return client.Client(api_version,
                             monasca_url,
                             token=token,
                             insecure=get_conf("insecure"),
                             user_agent=api.USER_AGENT)

    def _get_time_series(self, end_time, interval, ret_fields_mapping, period):
        resp_dict = {}
        ret_list = []
        te = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%SZ")
        ts = te + timedelta(hours=-int(interval))
        for fields in ret_fields_mapping.iteritems():
            local_fields = copy.deepcopy(fields[1])
            local_fields["start_time"] = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            local_fields["period"] = int(period)
            local_fields["end_time"] = end_time
            resp_dict = self.monasca_client.metrics.list_statistics(
                **local_fields)
            ret_list.append(resp_dict)
        return ret_list

    def _get_monasca_aggregated_data(self, end_time, interval,
                                     ret_fields_mapping):
        resp_dict = {}
        ret_list = []
        te = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%SZ")
        ts = te + timedelta(hours=-int(interval))
        start_time = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        for fields in ret_fields_mapping.iteritems():
            local_fields = copy.deepcopy(fields[1])
            local_fields["start_time"] = start_time
            local_fields["end_time"] = end_time
            resp_dict = self.monasca_client.metrics.list_measurements(
                **local_fields)
            ret_list.append(resp_dict)
        return ret_list

    def _get_monasca_formatted_data(self, output, end_time, interval, period):
        spec = {}
        interval = int(interval)
        for i in output:
            try:
                stat = i[0]['statistics']
                if interval == 1:
                    spec[i[0]['name']] = stat[-1][1]
                else:
                    spec[i[0]['name']] = self._handle_monasca_no_values(
                        end_time, stat, interval, period)
            except (TypeError, IndexError, KeyError):
                pass
        return spec

    def _get_file_system_mount_point(self, cluster, hostname):
        ret_list = []
        metric_list = \
            self.monasca_client.metrics.list(
                name="swiftlm.systems.check_mounts",
                dimensions={"service": "object-storage",
                            "hostname": hostname,
                            "cluster": cluster})
        for metric in metric_list:
            ret_list.append(metric["dimensions"]["mount"])
        return ret_list

    def total_node(self):
        clusterwise_data = self.call_service(target="catalog",
                                             operation="get_swift_clusters")
        resp_dict = {}
        for i in clusterwise_data.iteritems():
            resp_dict[i[0].split(":")[1]] = i[1]
        return resp_dict

    @expose()
    def storage(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        cluster = self.request[api.DATA][api.DATA]["cluster"]
        hostname = self.request[api.DATA][api.DATA]["hostname"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "percentage_usage": {
                "name": "swiftlm.diskusage.host.val.usage",
                "dimensions": {"service": "object-storage",
                               "cluster": cluster,
                               "hostname": hostname
                               },
                "statistics": "max",
                "merge_metrics": "true"
            },
            "used": {
                "name": "swiftlm.diskusage.host.val.used",
                "dimensions": {"service": "object-storage",
                               "cluster": cluster,
                               "hostname": hostname
                               },
                "statistics": "max",
                "merge_metrics": "true"
            },
            "total_usage": {
                "name": "swiftlm.diskusage.host.val.size",
                "dimensions": {"service": "object-storage",
                               "cluster": cluster,
                               "hostname": hostname
                               },
                "statistics": "max",
                "merge_metrics": "true"
            }
        }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        return self._get_monasca_formatted_data(output, end_time,
                                                interval, period)

    @expose()
    def memory(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        cluster = self.request[api.DATA][api.DATA]["cluster"]
        hostname = self.request[api.DATA][api.DATA]["hostname"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "total": {
                "name": "mem.total_mb",
                "dimensions": {"service": "system",
                               "cluster": cluster,
                               "hostname": hostname
                               },
                "statistics": "max",
                "merge_metrics": "true"
            },
            "free": {
                "name": "mem.free_mb",
                "dimensions": {"service": "system",
                               "cluster": cluster,
                               "hostname": hostname
                               },
                "statistics": "max",
                "merge_metrics": "true"
            },
        }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        return self._get_monasca_formatted_data(
            output, end_time, interval, period)

    @expose()
    def load_average_donut(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        cluster = self.request[api.DATA][api.DATA]["cluster"]
        hostname = self.request[api.DATA][api.DATA]["hostname"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "load_five_avg": {
                "name": "swiftlm.load.host.val.five",
                "dimensions": {"service": "object-storage",
                               "cluster": cluster,
                               "hostname": hostname
                               },
                "statistics": "max",
                "merge_metrics": "true"
            }
        }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        return self._get_monasca_formatted_data(
            output, end_time, interval, period)

    @expose()
    def time_to_replicate(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "replication_object_duration": {
                "name": "swiftlm.replication.cp.avg.object_duration",
                "dimensions": {"service": "object-storage"},
                "statistics": "max",
                "merge_metrics": "true"
            },
            "replication_account_duration": {
                "name": "swiftlm.replication.cp.avg.account_duration",
                "dimensions": {"service": "object-storage"},
                "statistics": "max",
                "merge_metrics": "true"
            },
            "replication_container_duration": {
                "name": "swiftlm.replication.cp.avg.container_duration",
                "dimensions": {"service": "object-storage"},
                "statistics": "max",
                "merge_metrics": "true"
            }
        }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        return self._get_monasca_formatted_data(
            output, end_time, interval, period)

    @expose()
    def oldest_replication_completion(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "replication_object_last": {
                "name": "swiftlm.replication.cp.max.object_last",
                "dimensions": {"service": "object-storage"},
                "statistics": "max",
                "merge_metrics": "true"
            },
            "replication_account_last": {
                "name": "swiftlm.replication.cp.max.account_last",
                "dimensions": {"service": "object-storage"},
                "statistics": "max",
                "merge_metrics": "true"
            },
            "replication_container_last": {
                "name": "swiftlm.replication.cp.max.container_last",
                "dimensions": {"service": "object-storage"},
                "statistics": "max",
                "merge_metrics": "true"
            }
        }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        return self._get_monasca_formatted_data(
            output, end_time, interval, period)

    @expose()
    def current_capacity(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "total_size": {"name": "swiftlm.diskusage.val.size_agg",
                           "dimensions": {"host": "all"},
                           "statistics": "max",
                           "merge_metrics": "true"},
            "avail_size": {"name": "swiftlm.diskusage.val.avail_agg",
                           "dimensions": {"host": "all"},
                           "statistics": "max",
                           "merge_metrics": "true"}}
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        return self._get_monasca_formatted_data(
            output, end_time, interval, period)

    @expose()
    def rate_of_change(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "diskusage-used": {
                "name": "swiftlm.diskusage.rate_agg",
                "dimensions": {"host": "all"},
                "statistics": "max",
                "merge_metrics": "true"
            }
        }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        try:
            stat = output[0][0]['statistics']
            if int(interval) == 1 or int(interval) == 2:
                if len(stat) > 1:
                    return [stat[-1][1] - stat[-2][1]]
                else:
                    return [stat[-1][1]]
            else:
                value = []
                for j in range(0, len(stat) - 1):
                    temp = []
                    temp.append(stat[j][0])
                    temp.append(int(stat[j + 1][1]) -
                                int(stat[j][1]))
                    value.append(temp)
                return (self._handle_monasca_no_values(end_time,
                                                       value,
                                                       interval,
                                                       period))
        except (TypeError, IndexError, KeyError):
            return [-1]

    @expose()
    def filesystem_utilization(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        cluster = self.request[api.DATA][api.DATA]["cluster"]
        hostname = self.request[api.DATA][api.DATA]["hostname"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "filesystem_utilization_min": {
                "name": "swiftlm.diskusage.host.min.usage",
                "dimensions": {"service": "object-storage",
                               "hostname": hostname,
                               "cluster": cluster
                               },
                "merge_metrics": "true",
                "statistics": "min"
            },
            "filesystem_utilization_max": {
                "name": "swiftlm.diskusage.host.max.usage",
                "dimensions": {"service": "object-storage",
                               "hostname": hostname,
                               "cluster": cluster
                               },
                "merge_metrics": "true",
                "statistics": "max"
            },
            "filesystem_utilization_main": {
                "name": "swiftlm.diskusage.host.val.usage",
                "dimensions": {"service": "object-storage",
                               "cluster": cluster,
                               "hostname": hostname
                               },
                "statistics": "max",
                "merge_metrics": "true"
                }
        }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        return self._get_monasca_formatted_data(
            output, end_time, interval, period)

    @expose()
    def latency_healthcheck(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "healthcheck_latency_avg": {
                "name": "swiftlm.umon.target.avg.latency_sec",
                "dimensions": {
                    "component": "healthcheck-api",
                    "service": "object-storage"
                },
                "statistics": "avg",
                "merge_metrics": "true"
            },
            "healthcheck_latency_min": {
                "name": "swiftlm.umon.target.min.latency_sec",
                "dimensions": {
                    "component": "healthcheck-api",
                    "service": "object-storage"
                    },
                "statistics": "min",
                "merge_metrics": "true"
            },
            "healthcheck_latency_max": {
                "name": "swiftlm.umon.target.max.latency_sec",
                "dimensions": {
                    "component": "healthcheck-api",
                    "service": "object-storage"
                    },
                "statistics": "max",
                "merge_metrics": "true"
            }
        }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        return self._get_monasca_formatted_data(
            output, end_time, interval, period)

    @expose()
    def latency_operational(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "operational_latency_avg": {
                "name": "swiftlm.umon.target.avg.latency_sec",
                "dimensions": {
                    "component": "rest-api",
                    "service": "object-storage"},
                "statistics": "avg",
                "merge_metrics": "true"
            },
            "operational_latency_min": {
                "name": "swiftlm.umon.target.min.latency_sec",
                "dimensions": {
                    "component": "rest-api",
                    "service": "object-storage"},
                "statistics": "min",
                "merge_metrics": "true"
            },
            "operational_latency_max": {
                "name": "swiftlm.umon.target.max.latency_sec",
                "dimensions": {
                    "component": "rest-api",
                    "service": "object-storage"},
                "statistics": "max",
                "merge_metrics": "true"
            }
        }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        return self._get_monasca_formatted_data(
            output, end_time, interval, period)

    @expose()
    def async_pending(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "async_pending_max": {
                "name": "swiftlm.async_pending.cp.total.queue_length",
                "dimensions": {
                    "service": "object-storage"
                    },
                "statistics": "max",
                "merge_metrics": "true"
            }
        }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        return self._get_monasca_formatted_data(
            output, end_time, interval, period)

    @expose()
    def alarms(self):
        resp_dict = self.monasca_client.alarms.count(
            metric_dimensions={"service": "object-storage"},
            group_by="state")
        return resp_dict

    @expose()
    def alarm_description(self):
        cluster = self.request[api.DATA][api.DATA]["cluster"]
        hostname = self.request[api.DATA][api.DATA]["hostname"]
        ids = []
        resp_dict = {}
        final_dict = {}
        alarms_list = \
            self.monasca_client.alarms.list(
                metric_dimensions={"service": "object-storage",
                                   "hostname": hostname,
                                   "cluster": cluster})
        for alarm in alarms_list:
            ids.append(alarm['id'])
        for id in ids:
            id = str(id)
            try:
                resp_dict[id] = self.monasca_client.alarms.get(alarm_id=id)
                final_dict[id] = {}
                final_dict[id]['name'] = \
                    resp_dict[id]['alarm_definition']['name']
                final_dict[id]['severity'] = \
                    resp_dict[id]['alarm_definition']['severity']
                final_dict[id]['alarm_definition_id'] = \
                    resp_dict[id]['alarm_definition']['id']
                final_dict[id]['state'] = \
                    resp_dict[id]['state']
                resp_dict[id]['details'] = \
                    self.monasca_client.alarm_definitions.get(
                        alarm_id=final_dict[id]['alarm_definition_id'])
                final_dict[id]['description'] = \
                    resp_dict[id]['details']['description']
                if resp_dict[id]['state'] == "UNDETERMINED":
                    final_dict[id]['status'] = "UNKNOWN"
                elif resp_dict[id]['state'] == "OK":
                    final_dict[id]['status'] = "OK"
                elif resp_dict[id]['state'] == "ALARM" and \
                    resp_dict[id]['alarm_definition'][
                        'severity'] in ("CRITICAL", "HIGH"):
                        final_dict[id]['status'] = "CRITICAL"
                elif resp_dict[id]['state'] == "ALARM" and \
                    resp_dict[id]['alarm_definition'][
                        'severity'] in ("MEDIUM", "LOW"):
                        final_dict[id]['status'] = "WARNING"
            except (TypeError, IndexError, KeyError):
                final_dict[id] = {}
        return final_dict

    @expose()
    def file_systems(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        cluster = self.request[api.DATA][api.DATA]["cluster"]
        hostname = self.request[api.DATA][api.DATA]["hostname"]
        period = self.request[api.DATA][api.DATA]["period"]
        resp_dict = {}
        mount_point = self._get_file_system_mount_point(cluster, hostname)
        for mount in mount_point:
            ret_fields_mapping = {
                "total": {
                    "name": "swiftlm.diskusage.host.val.size",
                    "dimensions": {"service": "object-storage",
                                   "hostname": hostname,
                                   "cluster": cluster,
                                   "mount": mount
                                   },
                    "statistics": "max",
                    "merge_metrics": "true"
                    },
                "used": {
                    "name": "swiftlm.diskusage.host.val.used",
                    "dimensions": {"service": "object-storage",
                                   "hostname": hostname,
                                   "cluster": cluster,
                                   "mount": mount
                                   },
                    "statistics": "max",
                    "merge_metrics": "true"
                    },
                "percentage_utilized": {
                    "name": "swiftlm.diskusage.host.val.usage",
                    "dimensions": {"service": "object-storage",
                                   "hostname": hostname,
                                   "cluster": cluster,
                                   "mount": mount
                                   },
                    "statistics": "max",
                    "merge_metrics": "true"
                    },
                "mount_status": {
                    "name": "swiftlm.systems.check_mounts",
                    "dimensions": {"service": "object-storage",
                                   "cluster": cluster,
                                   "hostname": hostname,
                                   "mount": mount
                                   },
                    "statistics": "max",
                    "merge_metrics": "true"
                }
            }
            output = self._get_time_series(end_time, interval,
                                           ret_fields_mapping, period)
            resp_dict[mount] = self._get_monasca_formatted_data(output,
                                                                end_time,
                                                                interval,
                                                                period)
        return resp_dict

    @expose()
    def mount_status(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        cluster = self.request[api.DATA][api.DATA]["cluster"]
        hostname = self.request[api.DATA][api.DATA]["hostname"]
        period = self.request[api.DATA][api.DATA]["period"]
        resp_dict = {}
        resp_dict['mount_status'] = dict(mounted=0, unmounted=0)
        mount_point = self._get_file_system_mount_point(cluster, hostname)
        mount_point_flag = False
        resp_dict['total_mount_point'] = len(mount_point)
        for mount in mount_point:
            ret_fields_mapping = {
                "mount_status": {
                    "name": "swiftlm.systems.check_mounts",
                    "dimensions": {"service": "object-storage",
                                   "cluster": cluster,
                                   "hostname": hostname,
                                   "mount": mount
                                   },
                    "statistics": "max",
                    "merge_metrics": "true"
                }
            }
            output = self._get_time_series(end_time, interval,
                                           ret_fields_mapping, period)
            for i in output:
                try:
                    stat = i[0]['statistics']
                    if stat[-1][1] == 0.0:
                        resp_dict['mount_status']['mounted'] = \
                            resp_dict['mount_status']['mounted'] + 1
                    elif stat[-1][1] == 2.0:
                        resp_dict['mount_status']['unmounted'] = \
                            resp_dict['mount_status']['unmounted'] + 1
                except (TypeError, IndexError, KeyError):
                    continue
            mount_point_flag = True
        if not mount_point_flag:
            return dict(mounted=-1, unmounted=-1, total_mount_point=-1)
        return resp_dict

    @expose()
    def service_availability(self):
        """

        Request format::

            "target": "objectstorage_summary",
            "operation": "service_availability",

        """
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "service_availability": {
                "name": "swiftlm.umon.target.val.avail_day",
                "dimensions": {"component": "rest-api",
                               "service": "object-storage"},
                "statistics": "max",
                "merge_metrics": "true"
            }
        }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        if output:
            return self._get_monasca_formatted_data(
                output, end_time, interval, period)
        else:
            return {}

    @expose()
    def load_average(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]
        ret_fields_mapping = {
            "load_avg": {
                "name": "swiftlm.load.cp.avg.five",
                "dimensions": {"service": "object-storage"},
                "statistics": "avg",
                "merge_metrics": "true"
                },
            "load_min": {
                "name": "swiftlm.load.cp.min.five",
                "dimensions": {"service": "object-storage"},
                "statistics": "min",
                "merge_metrics": "true"
                },
            "load_max": {
                "name": "swiftlm.load.cp.max.five",
                "dimensions": {"service": "object-storage"},
                "statistics": "max",
                "merge_metrics": "true"
                }
            }
        output = self._get_time_series(end_time, interval,
                                       ret_fields_mapping, period)
        return self._get_monasca_formatted_data(
            output, end_time, interval, period)

    @expose(is_long=True)
    def heat_map_utilization_focused_inventory(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        cluster_node_info = self.total_node()
        resp_dict = {}
        metric_name_size = "swiftlm.diskusage.val.size_agg"
        metric_name_avail = "swiftlm.diskusage.val.avail_agg"
        for cluster, host_list in cluster_node_info.iteritems():
            resp_dict[cluster] = {}
            for host in host_list:
                resp_dict[cluster][host] = {}
                ret_fields_mapping = {
                    "diskusage_used": {"name": metric_name_size,
                                       "dimensions": {"aggregation_period":
                                                      "hourly", "host": host}},
                    "diskusage_avail": {"name": metric_name_avail,
                                        "dimensions": {"aggregation_period":
                                                       "hourly", "host": host}}
                }
                output = self._get_monasca_aggregated_data(end_time, interval,
                                                           ret_fields_mapping)
                try:
                    for mon_data in output:
                        resp_dict[cluster][host][mon_data[0]["name"]] = (
                            mon_data[0]["measurements"][-1][1])
                except (TypeError, IndexError, KeyError):
                    resp_dict[cluster][host] = -1
        self.update_job_status(percentage_complete=60)
        return resp_dict

    @expose(is_long=True)
    def heat_map_cpu_load_average(self):
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]
        cluster_node_info = self.total_node()
        final = {}
        for cluster, host_list in cluster_node_info.iteritems():
            final[cluster] = {}
            for host in host_list:
                ret_fields_mapping = {
                    "load_five_avg": {
                        "name": "swiftlm.load.host.val.five",
                        "dimensions": {"service": "object-storage",
                                       "cluster": cluster,
                                       "hostname": host
                                       },
                        "statistics": "max",
                        "merge_metrics": "true"
                    }}
                output = self._get_time_series(end_time, interval,
                                               ret_fields_mapping, period)
                try:
                    host_value = self._get_monasca_formatted_data(
                        output, end_time, interval, period)
                    if not host_value:
                        final[cluster][host] = -1
                    else:
                        final[cluster][host] = \
                            host_value['swiftlm.load.host.val.five']
                except (TypeError, IndexError, KeyError):
                    final[cluster][host] = -1
        self.update_job_status(percentage_complete=60)
        return final

    @expose(is_long=True)
    def node_state(self):
        cluster_node_info = self.total_node()
        final_dict = {}
        total_nodes = {"red": 0, "yellow": 0,
                       "green": 0, "grey": 0, "nodes": 0}
        for cluster, host_list in cluster_node_info.iteritems():
            final_dict[cluster] = {"red": 0, "green": 0,
                                   "grey": 0, "yellow": 0, "nodes": 0}
            for host in host_list:
                resp_dict = self.monasca_client.alarms.count(
                    metric_dimensions={"service": "object-storage",
                                       "hostname": host,
                                       "cluster": cluster},
                    group_by="state,severity")
                try:
                    total_nodes["nodes"] += 1
                    severity_dict = {"red": 0, "green": 0,
                                     "grey": 0, "yellow": 0}
                    alarms = resp_dict['counts']
                    for value, alarm, severity in alarms:
                        if alarm == "UNDETERMINED":
                            severity_dict["grey"] += 1
                        elif alarm == "ALARM" and severity in ("HIGH",
                                                               "CRITICAL"):
                            severity_dict["red"] += 1
                        elif alarm == "ALARM" and severity in ("MEDIUM",
                                                               "LOW"):
                            severity_dict["yellow"] += 1
                        elif alarm == "OK":
                            severity_dict["green"] += 1
                        else:
                            severity_dict["grey"] += 1
                except (TypeError, IndexError, KeyError):
                    severity_dict["grey"] += 1
                for severity in ('red', 'yellow', 'green', 'grey'):
                    if severity_dict[severity] > 0:
                        final_dict[cluster][severity] += 1
                        final_dict[cluster]["nodes"] += 1
                        total_nodes[severity] += 1
                        break
        final_dict["total_nodes"] = total_nodes
        self.update_job_status(percentage_complete=60)
        return final_dict

    @expose(is_long=True)
    def health_focused(self):
        cluster_node_info = self.total_node()
        final_dict = {}
        for cluster, host_list in cluster_node_info.iteritems():
            final_dict[cluster] = {}
            for host in host_list:
                resp_dict = self.monasca_client.alarms.count(
                    metric_dimensions={"service": "object-storage",
                                       "hostname": host,
                                       "cluster": cluster},
                    group_by="state,severity")
                try:
                    final_dict[cluster][host] = {"red": 0, "green": 0,
                                                 "grey": 0, "yellow": 0}
                    alarms = resp_dict['counts']
                    for value, alarm, severity in alarms:
                        if alarm == "UNDETERMINED":
                            final_dict[cluster][host]["grey"] += int(value)
                        elif alarm == "ALARM" and severity in ("HIGH",
                                                               "CRITICAL"):
                            final_dict[cluster][host]["red"] += int(value)
                        elif alarm == "ALARM" and severity in ("MEDIUM",
                                                               "LOW"):
                            final_dict[cluster][host]["yellow"] += (
                                int(value))
                        elif alarm == "OK":
                            final_dict[cluster][host]["green"] += int(value)
                except (TypeError, IndexError, KeyError):
                    final_dict[cluster][host]["grey"] = -1
        self.update_job_status(percentage_complete=60)
        return final_dict

    def _get_keystone_projects(self, ids=None):
        # ids= ["monasca", "admin"] OR "None"
        # return [{"name":"admin", "id":"5678h6"},
        #         {"name":"monasca", "id":"4673h2"}]
        ks_projects = self.call_service(target="user_group",
                                        operation="project_list")
        if not ids or ids == "None":
            return ks_projects
        else:
            return [p for p in ks_projects if p['name'] in ids]

    @expose()
    def project_list(self):
        """
        Returns a list of projects from keystone.

        .. deprecated:: 1.0
           Use :py:meth:`~.UserGroupSvc.get_project_list` instead.

        The ``ids`` field in the request can either be a list of projects
        of the string ``"None"`` (which will return all projects)

        Request format::

            "target": "objectstorage_summary",
            "operation": "project_list",
            "ids": "None"

        Response format::

            "data":[
              {"name": "admin", "id": "8e3a82a61ff74d84ab52aafcc6249e71"},
              {"name": "demo", "id": "19239852352358e9a89f989fa7a9aaee"}
              ...
            ]
        """
        try:
            ids = self.request[api.DATA][api.DATA]["ids"]
            return self._get_keystone_projects(ids)
        except Exception as e:
            LOG.exception("Error occurred: %s" % e)

    def _get_project_capacity(self, project_id, end_time, interval, period):

        # Project capacity for given project
        metric_name = None
        if project_id == "all":
            metric_name = "storage.objects.size_agg"
        else:
            metric_name = "storage.objects.size"
        ret_fields_mapping = {
            "replication_object_duration": {
                "name": metric_name,
                "dimensions": {"project_id": project_id},
                "statistics": "max",
                "merge_metrics": "true"
            }
        }
        return self._get_time_series(end_time, interval, ret_fields_mapping,
                                     period)

    @expose(is_long=True)
    def topten_project_capacity(self):
        """
        Returns the top ten projects sorted by storage capacity.

        Request format::

            "target": "objectstorage_summary",
            "operation": "topten_project_capacity",
            "end_time": "2016-12-25T00:00:00Z",
            "interval": "72",
            "period": "3600"

        Response format::

            "data": [
               {"swift-monitor": {"id": "857dedf742e94deaad5591720649898c",
                                  "value": -1}},
               {"monitor": {"id": "91aa65fb59d9416aac6d62d20a7e8064",
                                  "value": -1}},
               ...
            ]
        """

        try:
            end_time = self.request[api.DATA][api.DATA]["end_time"]
            interval = self.request[api.DATA][api.DATA]["interval"]
            period = self.request[api.DATA][api.DATA]["period"]

            proj_capacities = []
            for project in self._get_keystone_projects():
                capacity = self._get_project_capacity(project['id'],
                                                      end_time, interval,
                                                      period)
                try:
                    val = capacity[0][0]['statistics'][-1][-1]
                except (TypeError, IndexError, KeyError):
                    val = -1
                proj_cap = {project['name']: {"id": project['id'],
                                              "value": val}}
                proj_capacities.append(proj_cap)
            # Sort by value field in each project's dictionary
            sorted_projects = sorted(proj_capacities,
                                     key=lambda c: c.values()[0]['value'],
                                     reverse=True)
            self.update_job_status(percentage_complete=60)
            return sorted_projects[:10]
        except Exception as e:
            LOG.exception("Error occurred: %s" % e)

    def _handle_monasca_no_values(self, end_time, monasca_statistics,
                                  interval, period):
        """
        Given a [timestamp, measurement_value] from monasca, this method
        assigns default -1 value for all the timestamps within the range of
        start and end time where monasca does not give any value
        """
        format_out = "%Y-%m-%dT%H:%M:%SZ"
        format_in = "%Y-%m-%dT%H:%M:%S.%fZ"

        # end_time should be formatted without subsecond precision
        end = datetime.strptime(end_time, format_out)
        curr = end - timedelta(hours=float(interval))
        increment = timedelta(seconds=float(period))

        statistics = []
        stat = iter(monasca_statistics)

        next_avail = stat.next()
        next_avail_end = datetime.strptime(next_avail[0], format_in)
        while curr <= end:
            if curr < next_avail_end:
                statistics.append([curr.strftime(format_out), -1])
            else:
                statistics.append(next_avail)
                try:
                    next_avail = stat.next()
                    next_avail_end = datetime.strptime(next_avail[0],
                                                       format_in)
                except StopIteration:
                    # set next_avail_end beyond the end time of interest
                    next_avail_end = end + increment

            curr += increment

        return statistics

    @expose(is_long=True)
    def project_capacity(self):
        id = self.request[api.DATA][api.DATA]["id"]
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]

        capacity = self._get_project_capacity(id, end_time, interval, period)
        self.update_job_status(percentage_complete=60)
        try:
            stats = capacity[0][0]['statistics']
            if int(interval) == 1:
                return [int(stats[0][-1])]
            else:
                return self._handle_monasca_no_values(
                    end_time, stats, interval, period)
        except (TypeError, IndexError, KeyError):
            return [-1]

    @expose(is_long=True)
    def project_capacity_roc(self):
        id = self.request[api.DATA][api.DATA]["id"]
        end_time = self.request[api.DATA][api.DATA]["end_time"]
        interval = self.request[api.DATA][api.DATA]["interval"]
        period = self.request[api.DATA][api.DATA]["period"]
        capacity = self._get_project_capacity(id, end_time, interval, period)
        self.update_job_status(percentage_complete=60)
        try:
            stats = capacity[0][0]['statistics']
            if int(interval) == 2:
                return [int(stats[-1][1]) - int(stats[-2][1])]
            else:
                value = []
                for i in range(0, len(stats) - 1):
                    temp = []
                    temp.append(stats[i][0])
                    temp.append(int(stats[i + 1][1]) - int(stats[i][1]))
                    value.append(temp)
                return self._handle_monasca_no_values(end_time, value,
                                                      interval, period)
        except (TypeError, IndexError, KeyError):
            return [-1]

    @classmethod
    def needs_services(cls):
        # Even though this module does not use swift directly, it should
        # be suppressed if swift is not running, since the monitoring data
        # would be void and meaningless
        return ['monitoring', 'swift']
