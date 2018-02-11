# (c) Copyright 2015-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017-2018 SUSE LLC

import logging
from datetime import datetime, timedelta

from bll import api
from bll.plugins.monitor_service import TYPE_UNKNOWN
from bll.plugins.service import SvcBase, expose


LOG = logging.getLogger(__name__)

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
METRICS_MAP = {'cpu.system_perc': USED_CPU_PERC,
               'mem.total_mb': TOTAL_MEMORY_MB,
               'disk.total_used_space_mb': USED_STORAGE_MB,
               'disk.total_space_mb': TOTAL_STORAGE_MB,
               'mem.usable_mb': USABLE_MEMORY_MB}

# The possible VM types returned by nova are defined in
#  https://github.com/openstack/nova/blob/master/nova/compute/hv_type.py .
# This mapping converts nova types into the ones that the UI expects
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

NOVA_DETAIL_DATA = {'allocated_cpu': -1,
                    'allocated_memory': -1,
                    'allocated_storage': -1,
                    'cloud_external_interface': '',
                    'cloud_trunk': '',
                    'cloud_trunk_interface': '',
                    'hypervisor': '',
                    'hypervisor_display_name': '',
                    'hypervisor_hostname': '',
                    'hypervisor_id': "UNSET",
                    'id': '',
                    'instances': -1,
                    'name': '',
                    'ping_status': TYPE_UNKNOWN,
                    'progress': 0,
                    'region': '',
                    'service_host': '',
                    'state': '',
                    'status': TYPE_UNKNOWN,
                    'technology': '',
                    'total_cpu': -1,
                    'total_memory': -1,
                    'total_storage': -1,
                    'type': ''}

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

    @expose()
    def get_compute_list(self):
        """
        Gets the list of compute hosts.  The list of hypervisors is
        first retrieved from nova.

        Request format::

            "target": "compute",
            "operation": "get_compute_list"
        """
        if 'hypervisor-list' in self.data:
            nova_hyp_list = self.data['hypervisor-list']
        else:
            nova_hyp_list = self.call_service(target='nova',
                                              operation='hypervisor-list',
                                              data={'include_status': True})

        nova_compute_list = self.get_compute_data(nova_hyp_list, True)
        nova_compute_list = \
            self._filter_out_hosts(nova_compute_list, 'type', 'ironic')

        return nova_compute_list

    @expose('details')
    def get_compute_details(self):
        """
        Obtains details of the given compute host.  Monasca, nova,
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
        return self._get_resource_details(type, id)

    @staticmethod
    def _filter_out_hosts(compute_list, type, value):
        new_compute_list = []
        for hypervisor in compute_list:
            if hypervisor[type] != value:
                new_compute_list.append(hypervisor)
        return new_compute_list

    def _get_utilization(self, resource_type, **data):
        results = {}
        try:
            if resource_type in ["rhel", "hlinux", "kvm"]:
                meas_results = \
                    self._get_monasca_meas_value(METRICS_MAP, data)
                if meas_results.get(USABLE_MEMORY_MB) >= 0 and \
                        meas_results.get(TOTAL_MEMORY_MB) > 0:
                    meas_results[USED_MEMORY_MB] = \
                        meas_results[TOTAL_MEMORY_MB] - \
                        meas_results.get(USABLE_MEMORY_MB)
                if meas_results:
                    results.update(meas_results)
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

    def _get_resource_details(self, hypervisor_type, hypervisor_id):
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

        # esx hosts show up as hypervisor_hostname in nova but and as
        # service_host in "Ardana names" in monasca.  So we need this map to
        # translate the name back to a name that monasca recognizes
        esx_equiv_hosts = {host['service_host']: host['hypervisor_hostname']
                           for host in compute_list}

        for metric_name, ui_equiv in METRICS_MAP.iteritems():
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
                    if hostname not in esx_equiv_hosts:
                        continue
                    # We found an ESX host, so change it into a name that
                    # monasca recognizes
                    esx_cluster_id = esx_equiv_hosts[hostname]
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

    @classmethod
    def needs_services(cls):
        return ['compute', 'monitoring', 'ardana']
