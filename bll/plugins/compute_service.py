# (c) Copyright 2015-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

import hashlib
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from bll import api
from bll.common.util import is_legacy
from bll.plugins.monitor_service import TYPE_UNKNOWN
from bll.plugins.service import SvcBase, expose
from bll.common.util import is_stdcfg


LOG = logging.getLogger(__name__)

ENDPOINT_TYPE = u"esx_onboarder"

# Generic utilization metrics from monasca to be passed back to the UI
USED_CPU_PERC = 'used_cpu_perc'
USED_MEMORY_MB = 'used_memory_mb'
USED_STORAGE_MB = 'used_storage_mb'
TOTAL_MEMORY_MB = 'total_memory_mb'
TOTAL_STORAGE_MB = 'total_storage_mb'

# This is not passed back to UI, but used to calculate USED_MEMORY_MB
USABLE_MEMORY_MB = 'usable_memory_mb'

MONASCA_DETAIL_DATA = {USED_CPU_PERC: -1,
                       USED_MEMORY_MB: -1,
                       USED_STORAGE_MB: -1,
                       TOTAL_MEMORY_MB: -1,
                       TOTAL_STORAGE_MB: -1,
                       USABLE_MEMORY_MB: -1}
NON_EON_METRICS_MAP = {'cpu.system_perc': USED_CPU_PERC,
                       'mem.total_mb': TOTAL_MEMORY_MB,
                       'disk.total_used_space_mb': USED_STORAGE_MB,
                       'disk.total_space_mb': TOTAL_STORAGE_MB,
                       'mem.usable_mb': USABLE_MEMORY_MB}
EON_METRICS_MAP = {'vcenter.mem.total_mb': TOTAL_MEMORY_MB,
                   'vcenter.disk.total_used_space_mb': USED_STORAGE_MB,
                   'vcenter.cpu.used_perc': USED_CPU_PERC,
                   'vcenter.disk.total_space_mb': TOTAL_STORAGE_MB,
                   'vcenter.mem.used_mb': USED_MEMORY_MB}

# The possible VM types returned by nova are defined in
#  https://github.com/openstack/nova/blob/master/nova/compute/hv_type.py .
# This mapping converts nova types into the ones that eon returns
# and which the UI expects
TYPE_CLUSTER = 'cluster'
TYPE_KVM = 'kvm'
TYPE_HYPERV = 'hyperv'
NOVA_TYPE_MAPPINGS = {"hyperv": TYPE_HYPERV,
                      "kvm": TYPE_KVM,
                      "qemu": TYPE_KVM,
                      "vmware": TYPE_CLUSTER}
NOVA_STATUS_MAPPING = {"enabled": "ok",
                       "disabled": "error"}
NOVA_STATE_MAPPING = {"up": "activated",
                      "down": "deactivated"}
NOVA_DATA = {'allocated_cpu': -1,
             'allocated_memory': -1,
             'allocated_storage': -1,
             'total_cpu': -1,
             'total_memory': -1,
             'total_storage': -1,
             'instances': -1,
             'ping_status': TYPE_UNKNOWN,
             'hypervisor_hostname': '',
             'service_host': '',
             "region": ''}
EON_DATA = {'name': '',
            'hypervisor': '',
            'hypervisor_display_name': '',
            'type': '',
            'state': '',
            'id': '',
            'progress': 0,
            'hypervisor_id': "UNSET",
            'cloud_trunk': '',
            'cloud_trunk_interface': '',
            'cloud_external_interface': '',
            'technology': '',
            'status': TYPE_UNKNOWN}
NOVA_DETAIL_DATA = dict(EON_DATA.items() + NOVA_DATA.items())
HYPERVISOR_DISPLAYNAME_MAPPINGS = {TYPE_CLUSTER: 'ESXi',
                                   TYPE_KVM: 'KVM',
                                   TYPE_HYPERV: 'Hyper-V'}
HYPERVISOR_MAPPINGS = {TYPE_CLUSTER: 'esx'}
TECHNOLOGY_MAPPINGS = {TYPE_KVM: 'KVM',
                       TYPE_CLUSTER: 'VMWARE',
                       TYPE_HYPERV: 'Microsoft'}


class ComputeSvc(SvcBase):
    """
    The ``target`` value for this plugin is ``compute``. See :ref:`rest-api`
    for a full description of the request and response formats.
    """
    def __init__(self, *args, **kwargs):
        '''
        Set default values for service.
        '''
        super(ComputeSvc, self).__init__(*args, **kwargs)
        self.has_eon = self.token_helper.get_service_endpoint(ENDPOINT_TYPE)

    @expose()
    def get_compute_list(self):
        """
        Gets the list of compute hosts.  The list of hypervisors is
        first retrieved from nova.  If eon is available, then it may be
        able to access additional hypervisor hosts that nova cannot see;
        therefore its resource list is obtained, and any additional hosts
        are added to the results.

        Request format::

            "target": "compute",
            "operation": "get_compute_list"
        """
        compute_list = []
        if 'hypervisor-list' in self.data:
            nova_hyp_list = self.data['hypervisor-list']
        else:
            nova_hyp_list = self.call_service(target='nova',
                                              operation='hypervisor-list',
                                              data={'include_status': True})

        if self.has_eon:
            resource_list = self.call_service(target="eon",
                                              operation="resource_list")
            compute_list = self._filter_eon_compute_node(resource_list)
            self._update_eon_with_stats(compute_list, nova_hyp_list)

        if is_stdcfg():
            # In stdcfg, we create the compute list from EON and nova, but
            # in legacy, we should only get the compute list from EON.
            nova_compute_list = self.get_compute_data(nova_hyp_list, True)
            nova_compute_list = \
                self._filter_out_hosts(nova_compute_list, 'type', 'ironic')

            # merge nova_compute_list INTO eon_list
            compute_list = \
                self._merge_compute_hosts(nova_compute_list, compute_list)

        return compute_list

    @expose('details')
    def get_compute_details(self):
        """
        Obtains details of the given compute host.  Eon, monasca, nova,
        and ardana_service when available and necessary in order to get
        these details.

        Request format::

            "target": "compute",
            "operation": "details"
            "data" : { "data" : { "id" : "MYID", "type": "MYTYPE" }}
        """

        datadata = self.data.get(api.DATA)
        id = datadata.get("id")
        type = datadata.get("type")
        if self.has_eon and (is_legacy() or type == 'esxcluster'):
            return self._get_eon_resource_details(id, type)
        else:
            return self._get_non_eon_details(type, id)

    @staticmethod
    def _filter_out_hosts(compute_list, type, value):
        new_compute_list = []
        for hypervisor in compute_list:
            if hypervisor[type] != value:
                new_compute_list.append(hypervisor)
        return new_compute_list

    def _get_hash(self, data):
        return hashlib.sha1(data).hexdigest()

    def _get_eon_resource_details(self, resource_id, resource_type):
        resp_dict = {}
        tech = {'esxcluster': 'Vmware',
                'rhel': 'RedHat',
                'hyperv': 'Microsoft',
                'hlinux': 'Hewlett Packard Enterprise Linux'
                }
        resp_dict['monasca'] = MONASCA_DETAIL_DATA.copy()
        resp_dict['technology'] = tech[resource_type]
        self.server_id = None

        try:
            eon_response = self.call_service(target="eon",
                                             operation="resource_get",
                                             data={'id': resource_id})
            meta_dict = dict((m['name'], m['value'])
                             for m in eon_response['meta_data'])
        except Exception as e:
            self.response[api.DATA] = e.message
            self.response[api.STATUS] = api.STATUS_ERROR
            return {}

        if eon_response['state'] == "activated":
            if resource_type in ["hlinux", "kvm", "rhel", "hyperv"]:
                ardana_compute_name = eon_response['id']
                resp_dict['ardana'] = self.call_service(
                    target='ardana',
                    path="/model/entities/servers/" + ardana_compute_name)
            elif resource_type == "esxcluster":
                self.server_id = \
                    self._get_hash(eon_response['resource_mgr_id'] +
                                   meta_dict['cluster_moid'])
                hosts = eon_response.get("inventory", {}).get("hosts", [])
                resp_dict['host_count'] = len(hosts)
                if self.server_id is not None:
                    resp_dict['ardana'] = self.call_service(
                        target='ardana',
                        path="model/entities/servers/" + self.server_id)
                else:
                    self.response[api.DATA] = [
                        self._("{0}{1} - Could not get Ardana model "
                               "for Resource").format(resource_id,
                                                      eon_response['name'])]
                    self.response[api.STATUS] = api.STATUS_ERROR
                    return {}

                mgr_id = eon_response['resource_mgr_id']
                temp = self.call_service(target='eon',
                                         operation='get_resource_mgr',
                                         data={'id': mgr_id})
                resp_dict['vcenter_name'] = temp['name']

            hyp_list = self.call_service(target='nova',
                                         operation='hypervisor-list')

            try:
                hypervisor_id = int(meta_dict["hypervisor_id"])
            except ValueError:
                # Workaround for HEH-800 where hypervisor_id is improperly
                # set to "UNSET" for an activated ESX compute host
                # TODO: Remove this except block when eon team fixes HEH-800
                eon_host_name = '%s.%s' % (meta_dict['cluster_moid'],
                                           eon_response['resource_mgr_id'])
                hyp_dict = {host['name']: host['hypervisor_id']
                            for host in hyp_list}
                hypervisor_id = hyp_dict.get(eon_host_name, 0)

            hypervisor_host = ""
            for hyp in hyp_list:
                if hyp['region'] == eon_response['region'] and \
                    hyp['hypervisor_id'] == hypervisor_id:
                    hypervisor_host = hyp.get("name")
                    break
            if hypervisor_host:
                if resource_type == "esxcluster":
                    dimensions = {"esx_cluster_id": hypervisor_host}
                elif resource_type in ["rhel", "hlinux", "kvm"]:
                    dimensions = {"hostname": hypervisor_host}
                monasca_data = self._get_utilization(resource_type,
                                                     dimensions=dimensions)
                if monasca_data:
                    resp_dict.get('monasca').update(monasca_data)
        else:
            if resource_type == "esxcluster":
                mgr_id = eon_response['resource_mgr_id']
                temp = self.call_service(target='eon',
                                         operation='get_resource_mgr',
                                         data={'id': mgr_id})
                resp_dict['vcenter_name'] = temp['name']
                resp_dict['vcenter_id'] = mgr_id

        return resp_dict

    def _update_eon_with_stats(self, compute_list, hyp_list):

        for compute in compute_list:
            # move meta_data contents to the root of the compute dict
            if 'meta_data' in compute:
                for entry in compute['meta_data']:
                    compute[entry['name']] = entry['value']

                del compute['meta_data']

        # Convert hyp_list to a searchable hyp_dict
        hyp_dict = dict(("%s.%s" %
                        (hyp['hypervisor_id'], hyp['region']), hyp)
                        for hyp in hyp_list)

        for compute in compute_list:
            try:
                hypervisor_id = int(compute.get('hypervisor_id'))
            except (TypeError, ValueError):
                continue
            hypervisor_region = compute.get('region')
            hyp_dict_instance = {hyp['hypervisor_id']: hyp for hyp in hyp_list}
            compute['instances'] = hyp_dict_instance[int(hypervisor_id)
                                                     ]['instances']
            search_key = "%s.%s" % (hypervisor_id, hypervisor_region)
            for key in (NOVA_DATA.keys()):
                try:
                    compute[key] = hyp_dict[search_key][key]
                except KeyError:
                    # Gracefully handle missing search key
                    pass

    def _get_utilization(self, resource_type, **data):
        results = {}
        try:
            if resource_type in ["rhel", "hlinux", "kvm"]:
                meas_results = \
                    self._get_monasca_meas_value(NON_EON_METRICS_MAP, data)
                if meas_results.get(USABLE_MEMORY_MB) >= 0 and \
                        meas_results.get(TOTAL_MEMORY_MB) > 0:
                    meas_results[USED_MEMORY_MB] = \
                        meas_results[TOTAL_MEMORY_MB] - \
                        meas_results.get(USABLE_MEMORY_MB)
                if meas_results:
                    results.update(meas_results)
            elif resource_type == "esxcluster":
                metric_results = \
                    self._get_monasca_meas_value(EON_METRICS_MAP, data)
                if metric_results:
                    results.update(metric_results)
            return results
        except Exception as e:
            LOG.error(e.message)
            return None

    def _get_monasca_meas_value(self, metrics, dim):
        results = {}
        for metric_name in metrics:
            try:
                start_time = (datetime.utcnow() - timedelta(
                    minutes=5)).isoformat()
                data = {
                    'operation': 'measurement_list',
                    'name': metric_name,
                    'start_time': start_time,
                    'merge_metrics': True
                }

                # Get potential monasca parms we might need to provide
                data.update(dim)
                meas_list = self.call_service(
                    target='monitor',
                    data=data,
                )

                # There should only be one measurement list.
                # If not, it means our dimension filter is not strict enough
                if meas_list and len(meas_list) > 0:
                    meas = meas_list[0]
                    value_idx = meas['columns'].index('value')
                    # get the latest(last) measurement
                    val = meas['measurements'][-1][value_idx]
                    if isinstance(val, int) or isinstance(val, float):
                        results[metrics[metric_name]] = val
                    else:
                        results[metrics[metric_name]] = None
            except Exception as e:
                LOG.error("Error getting metric value for metric: "
                          "%s Reason: %s", metric_name, e.message)
                results[metrics[metric_name]] = None
        return results

    def get_compute_data(self, hyp_list=None, include_status=True):

        # Request a list of all hypervisors from nova.
        if not hyp_list:
            hyp_list = \
                self.call_service(target='nova',
                                  operation='hypervisor-list',
                                  data={'include_status': include_status})

        compute_list = []
        # Loop through nova_response and apply the relevant portions
        for hyp in hyp_list:
            compute_data = NOVA_DETAIL_DATA.copy()

            for k, v in hyp.iteritems():
                if k in compute_data:
                    compute_data[k] = v

            compute_data['id'] = compute_data['hypervisor_id']
            compute_data['type'] = compute_data['type'].lower()
            if compute_data['type'] in NOVA_TYPE_MAPPINGS:
                compute_data['type'] = NOVA_TYPE_MAPPINGS[compute_data['type']]

            compute_data['status'] = NOVA_STATUS_MAPPING.get(
                compute_data['status'], "unknown")

            if compute_data['state'] in NOVA_STATE_MAPPING:
                compute_data['state'] = NOVA_STATE_MAPPING.get(
                    compute_data['state'])

            compute_data['hypervisor'] = \
                HYPERVISOR_MAPPINGS.get(compute_data['type'],
                                        compute_data['type'])

            compute_data['hypervisor_display_name'] = \
                HYPERVISOR_DISPLAYNAME_MAPPINGS.get(compute_data['type'],
                                                    compute_data['type'])

            compute_data['technology'] = \
                TECHNOLOGY_MAPPINGS.get(compute_data['type'], '')

            compute_list.append(compute_data)

        return compute_list

    def _get_non_eon_details(self, hypervisor_type, hypervisor_id):
        details = {}

        # Monasca operates on dimensions, not hypervisor_id, so get hostname
        # and use it to determine utilization
        hyp_list = self.call_service(
            target='nova',
            operation='hypervisor-list'
        )
        hyp_dict = {hyp['hypervisor_id']: hyp for hyp in hyp_list}
        hostname = hyp_dict[int(hypervisor_id)]['name']
        details['instances'] = hyp_dict[int(hypervisor_id)]['instances']
        dim = {'hostname': hostname}
        details['monasca'] = \
            self._get_utilization(hypervisor_type, dimensions=dim)

        # Use the hostname to reverse-lookup the server name from the
        # config processor output's perspective
        server_info = self.call_service(
            target='ardana',
            path='/model/cp_output/server_info.yml'
        )
        cp_host = None
        for host, info in server_info.iteritems():
            if info['hostname'] == hostname:
                cp_host = host
                break
        if not cp_host:
            return details

        # Use the cp_host to get server-group and role-related data
        details['ardana'] = self.call_service(
            target='ardana',
            path="/model/entities/servers/" + cp_host
        )
        return details

    @expose()
    def get_cluster_utilization(self):
        """
        Gets cpu, memory, storage utilization for compute hosts, using
        information obtained from nova and monasca.

        Request format::

            "target": "compute",
            "operation": "get_cluster_utilization"
        """

        # hypervisor-list is used by many calls in this method.  Cache it
        # for use by others later.
        hyp_list = self.call_service(target='nova',
                                     operation='hypervisor-list',
                                     data={'include_status': True})
        self.data['hypervisor-list'] = hyp_list
        # first, get the compute clusters in the environment
        clusters = self.call_service(
            target='catalog',
            data={'operation': 'get_compute_clusters',
                  'hypervisor-list': hyp_list}
        )

        ############################################################
        # TODO: We also need to get rid of get_compute_data and just
        #       use get_compute_list.  They're very similar.
        ############################################################
        compute_list = self.get_compute_data(hyp_list=hyp_list)
        compute_list = self._filter_out_hosts(compute_list, 'type',
                                              'ironic')
        compute_list2 = self.get_compute_list()
        comp2_dict = {ch['service_host']: ch
                      for ch in compute_list2 if 'service_host' in ch}

        compute_hosts = {host['hypervisor_hostname']: host
                         for host in compute_list}

        # EON hosts show up as hypervisor_hostname in nova but and as
        # service_host in "Ardana names" in monasca.  So we need this map to
        # translate an EON name back to a name that monasca recognizes
        eon_equiv_hosts = {host['service_host']: host['hypervisor_hostname']
                           for host in compute_list}

        for metric_name, ui_equiv in NON_EON_METRICS_MAP.iteritems():
            # For each monasca metric, get all the measurements
            # across all hosts
            start_time = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
            meas_list = self.call_service(
                target='monitor',
                data={
                    'operation': 'measurement_list',
                    'name': metric_name,
                    'start_time': start_time,
                    'group_by': '*',
                    'merge_metrics': True
                }
            )
            for meas in meas_list:
                hostname = meas['dimensions']['hostname']
                if hostname not in compute_hosts:
                    if hostname not in eon_equiv_hosts:
                        continue
                    # We found an EON host, so change it into a name that
                    # monasca recognizes
                    esx_cluster_id = eon_equiv_hosts[hostname]
                    compute_hosts[hostname] = compute_hosts[esx_cluster_id]
                    del compute_hosts[esx_cluster_id]
                # The last measurement is the latest measurement
                value_idx = meas['columns'].index('value')
                compute_hosts[hostname][ui_equiv] = \
                    meas['measurements'][-1][value_idx]

        for hostname, meas in compute_hosts.iteritems():
            # There are no measurements for a deactivated host, so move on
            if meas['state'] == 'deactivated':
                continue

            # If a host has the USABLE_MEMORY_MB metric, calculate
            # USED_MEMORY_MB as this is what the UI uses.  Normally, the metric
            # is there unless the host is deactivate or monasca has problems.
            if USABLE_MEMORY_MB in meas:
                meas[USED_MEMORY_MB] = \
                    meas[TOTAL_MEMORY_MB] - meas[USABLE_MEMORY_MB]
                del compute_hosts[hostname][USABLE_MEMORY_MB]
                used_mem = float(meas[USED_MEMORY_MB])
                total_mem = float(meas[TOTAL_MEMORY_MB])
                meas['used_memory_perc'] = 100 * used_mem / total_mem

            if USED_STORAGE_MB in meas:
                used_stor = float(meas[USED_STORAGE_MB])
                total_stor = float(meas[TOTAL_STORAGE_MB])
                meas['used_storage_perc'] = 100 * used_stor / total_stor

        # Create a mapping to translate nova service_host to hostname
        host_hyp_dict = {host_info['service_host']: name
                         for name, host_info in compute_hosts.items()}

        results = {}
        for clust, host_list in clusters.iteritems():
            results[clust] = {}
            for host in host_list:
                if host in host_hyp_dict:
                    alt_host = host_hyp_dict[host]

                    # Replace name, id and type from the information in
                    # compute_list2
                    for key in ('name', 'id', 'type'):
                        compute_hosts[alt_host][key] = \
                            comp2_dict[host][key]
                    results[clust][host] = compute_hosts[alt_host]

        return results

    def _filter_eon_compute_node(self, node_list):
        compute_nodes = []
        for node in node_list:
            if node['type'] != 'baremetal':
                if node['state'] != 'provisioning':
                    compute_nodes.append(node)
                elif node['state'] == 'provisioning' and \
                    node['type'] == 'esxcluster':
                    compute_nodes.append(node)
        return compute_nodes

    def _merge_compute_hosts(self, nova_list, all_list):
        """
        For any compute host in the nova_list, add it to eon_list only if it is
        unique.  If a dupe is found, merge the host.
        This handles the case where 'eon resource-list' and
        'nova hypervisor-list' see the same compute host, but provide different
         results.
        """
        if not all_list:
            return nova_list

        # create a dict of region -> hypervisor_id -> host
        eon_hyp_dict = defaultdict(dict)
        # and a dict of eon hostname -> host
        eon_host_dict = {}
        for eon_host in all_list:
            region = eon_host.get('region')
            if not region:
                continue

            # Nova uses type int for hypervisor_id, but eon uses
            # a unicode string, so convert to a type int.
            try:
                hyp_id = int(eon_host.get('hypervisor_id'))
                eon_hyp_dict[region][hyp_id] = eon_host
            except (TypeError, ValueError):
                pass

            hostname = "%s.%s" % (eon_host.get('cluster_moid'),
                                  eon_host.get('resource_mgr_id'))
            eon_host_dict[hostname] = eon_host

        for nova_host in nova_list:
            region = nova_host['region']
            hyp_id = nova_host['hypervisor_id']
            hostname = nova_host['hypervisor_hostname']

            eon_host = None
            if region in eon_hyp_dict:
                eon_host = eon_hyp_dict[region].get(hyp_id)
            eon_host = eon_host or eon_host_dict.get(hostname)

            if not eon_host:
                all_list.append(nova_host)
            else:
                # we put almost everything from nova_host into eon_host except
                # for the keys in 'key_exceptions'
                key_exceptions = ('id', 'name', 'type', 'state')
                update_dict = {k: v
                               for k, v in nova_host.iteritems()
                               if k not in key_exceptions}
                eon_host.update(update_dict)

        return all_list

    @classmethod
    def needs_services(cls):
        # Note: eon is not required, but is used if available
        return ['compute', 'monitoring']
