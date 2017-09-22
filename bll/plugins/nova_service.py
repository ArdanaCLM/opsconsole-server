# (c) Copyright 2015-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

from collections import Counter
from datetime import timedelta, datetime
from time import sleep
from bll import api
from bll.common.util import get_conf
from bll.plugins import service
from bll.plugins.region_client import RegionClient
from novaclient.exceptions import NotFound
import logging
import requests

from novaclient import client as novaclient

LOG = logging.getLogger(__name__)

# Power states as defined in nova/nova/compute/power_state.py
power_states = {
    0: 'NO STATE',
    1: 'RUNNING',
    3: 'PAUSED',
    4: 'SHUTDOWN',
    6: 'CRASHED',
    7: 'SUSPENDED'
}

# instance list filters
FILTER_DBAAS = 'dbaas'
FILTER_MSGAAS = 'msgaas'
FILTER_CI = 'ci'
FILTER_PROJECT = 'project'


class NovaSvc(service.SvcBase):
    """
    The ``target`` value for this plugin is ``nova``. See :ref:`rest-api`
    for a full description of the request and response formats.
    """

    SUGGESTED_POLL_INTERVAL = 5

    def __init__(self, *args, **kwargs):
        """
        Initializer for the Nova Client Service
        """
        super(NovaSvc, self).__init__(*args, **kwargs)

        self.clients = RegionClient('compute', self._get_nova_client,
                                    self.token, self.region)

    def _get_nova_client(self, region=None, **kwargs):

        try:
            return novaclient.Client(
                "2",
                session=self.token_helper.get_session(),
                endpoint_type=get_conf("services.endpoint_type",
                                       default="internalURL"),
                region_name=region,
                user_agent=api.USER_AGENT)
        except Exception as e:
            LOG.error("Error creating nova client : %s ", e)
            raise requests.exceptions.HTTPError(e.message)

    @service.expose('hypervisor-stats')
    def hypervisor_stats(self):
        """
        Get the statistics for cpu, memory, and storage across all hypervisors.
        In a multi-region environment, if no specific region is requested, then
        data from all regions will be returned.

        Request format::

            "target": "nova",
            "operation": "hypervisor-stats"
        """
        req_keys = ('vcpus_used', 'vcpus',
                    'local_gb_used', 'local_gb',
                    'memory_mb_used', 'memory_mb')

        sums = {key: 0 for key in req_keys}
        for client, region in self.clients.get_clients():
            stats = client.hypervisors.statistics()

            for key in req_keys:
                sums[key] += getattr(stats, key, 0)

        # TODO: float is probably not necessary, check UI code
        return {
            'used': {
                'cpu': sums['vcpus_used'],
                'memory': sums['memory_mb_used'],
                'storage': sums['local_gb_used']
            },
            'total': {
                'cpu': float(sums['vcpus']),
                'memory': float(sums['memory_mb']),
                'storage': sums['local_gb']
            }
        }

    @service.expose('service-list')
    def service_list(self):
        """
        Return a list summarizing how many compute nodes are present,
        how many are up, and how many are in an error state.

        In a multi-region environment, if no specific region is requested,
        then data from all regions will be returned.

        Request format::

            "target": "nova",
            "operation": "service-list"
        """
        compute_list = []
        for client, region in self.clients.get_clients():
            compute_list.extend(client.services.list(binary="nova-compute"))

        up_nodes = len(
            [compute for compute in compute_list if compute.state == "up"])
        down_nodes = len(compute_list) - up_nodes

        return {"ok": up_nodes,
                "error": down_nodes,
                "total": len(compute_list)}

    def _get_historical_data(self, start_date, end_date, resources):
        startdate = datetime.strptime(start_date, "%Y-%m-%d")
        enddate = datetime.strptime(end_date, "%Y-%m-%d")

        resources_count = {}
        today = 0
        while startdate <= enddate:
            resources_count[enddate.isoformat()] = (today, 0)
            enddate = enddate + timedelta(days=-1)
            today = today - 1
        for resource in resources:
            event_date = datetime.strptime(resource[0], "%Y-%m-%d").isoformat()
            day, count = resources_count[event_date]
            resources_count[event_date] = day, resource[1]

        response = sorted(
            resources_count.values(), key=lambda tup: tup[0])
        average = round(
            (sum(x[1] for x in response) + 0.0) / len(resources_count), 2)
        data = {'data': response,
                'average': average}
        return data

    def _deleted_servers(self, start_date):
        options = {'all_tenants': True, 'deleted': True, "changes-since":
                   start_date, 'sort_key': 'deleted_at', 'sort_dir': 'asc'}
        deleted = []
        for client, region in self.clients.get_clients():
            servers = client.servers.list(search_opts=options)
            for server in servers:
                output = vars(server)
                deleted_at = output.get('OS-SRV-USG:terminated_at') or \
                    output.get('updated')
                if deleted_at:
                    deleted_at = deleted_at.split("T")[0]
                    deleted.append(deleted_at)

        deleted = Counter(deleted).items()
        return deleted

    def _created_servers(self, start_date):
        options = {'all_tenants': True, "changes-since": start_date,
                   'sort_key': 'created_at', 'sort_dir': 'asc'}
        created = []
        for client, region in self.clients.get_clients():
            servers = client.servers.list(search_opts=options)
            for server in servers:
                output = vars(server)
                launched_at = output.get('created') or \
                    output.get('OS-SRV-USG:launched_at')
                if launched_at:
                    launched_at = launched_at.split("T")[0]
                    if launched_at >= start_date:
                        created.append(launched_at)

        created = Counter(created).items()
        return created

    @service.expose('servers-list')
    def servers_list(self):
        """
        Get historical information about virtual machines created and deleted
        in a given time range.
        In a multi-region environment, if no specific region is requested, then
        data from all regions will be returned.

        Request format::

            "target": "nova",
            "operation": "servers-list",
            "start_date": "2016-01-01T00:00:00",
            "end_date": "2016-02-01T00:00:00"
        """
        start_date = self.request[api.DATA]['start_date']
        end_date = self.request[api.DATA]['end_date']
        start_date = datetime.strptime(
            start_date, "%Y-%m-%d").isoformat().split("T")[0]
        created_vms = self._created_servers(start_date)
        deleted_vms = self._deleted_servers(start_date)
        created_data = self._get_historical_data(
            start_date, end_date, created_vms)
        deleted_data = self._get_historical_data(
            start_date, end_date, deleted_vms)

        return {'created': created_data, 'deleted': deleted_data}

    @service.expose('hypervisor-list')
    def _hypervisor_list(self):
        """
        Get list of hypervisors with details, optionally including their ping
        status from monasca.
        In a multi-region environment, if no specific region is requested, then
        data from all regions will be returned.

        Request format::

            "target": "nova",
            "operation": "hypervisor-list",
            "include_status": True
        """
        ret_hyp_list = []
        include_status = self.data.get('include_status', True)
        for client, region in self.clients.get_clients():
            hypervisor_list = client.hypervisors.list(detailed=True)
            for hypervisor in hypervisor_list:
                hypervisor_data = {}
                hypervisor_data["allocated_cpu"] = hypervisor.vcpus_used
                hypervisor_data["total_cpu"] = hypervisor.vcpus
                hypervisor_data["allocated_memory"] = hypervisor.memory_mb_used
                hypervisor_data["total_memory"] = hypervisor.memory_mb
                hypervisor_data["allocated_storage"] = hypervisor.local_gb_used
                hypervisor_data["total_storage"] = hypervisor.local_gb
                hypervisor_data["instances"] = hypervisor.running_vms
                name = getattr(hypervisor, hypervisor.NAME_ATTR,
                               hypervisor.host_ip)
                hypervisor_data["name"] = name
                hypervisor_data["hypervisor_id"] = hypervisor.id
                hypervisor_data["status"] = hypervisor.status
                hypervisor_data["state"] = hypervisor.state
                hypervisor_data["type"] = hypervisor.hypervisor_type
                hypervisor_data["service_host"] = hypervisor.service['host']
                hypervisor_data["hypervisor_hostname"] = \
                    hypervisor.hypervisor_hostname
                hypervisor_data["region"] = region
                ret_hyp_list.append(hypervisor_data)

        # Get host_alive_status:ping results for all compute hosts found
        if include_status:
            hostnames = [hd['service_host'] for hd in ret_hyp_list]
            statuses = self.call_service(target='monitor',
                                         operation='get_appliances_status',
                                         data={
                                             'hostnames': hostnames
                                         })

            # Fill in the ping status details for each of the hosts
            for hyp in ret_hyp_list:
                hyp['ping_status'] = \
                    statuses.get(hyp['service_host'], 'unknown')

        return ret_hyp_list

    @service.expose('instance-list')
    def instance_list(self):
        """
        Get list of instances and their details.  If ``show_baremetal`` is
        set to ``False`` (the default), then baremetal instances will be
        excluded from the results.  ``filter`` can be provided to return only
        those instances that match the filter, which can have the values:
        ``dbaas``, ``msgaas``, ``ci``, and ``project``; if ``filter`` is
        ``project``, then an additional ``project_id`` field should be
        provided to control that filter.

        In a multi-region environment, if no specific region is requested, then
        data from all regions will be returned.

        Request format::

            "target": "nova",
            "operation": "instance-list",
            "show_baremetal": True or False,
            "filter": "dbaas"
        """
        # by default, don't show baremetal instances
        show_baremetal = self.data.get('show_baremetal', False)

        proj_list = self.call_service(target='user_group',
                                      operation='project_list')
        proj_dict = {item['id']: item['name'] for item in proj_list}

        # if the baremetal service is available and we don't want to see
        # baremetal instances, we'll need a list of baremetal instance uuids
        # so that they can be filtered from the server list
        bm_uuid_list = []

        baremetal_svc = self.token_helper.get_service_endpoint('baremetal')
        if baremetal_svc and not show_baremetal:
            bm_list = self.call_service(target='ironic',
                                        operation='node.list',
                                        region=self.region)
            bm_uuid_list = [bmi['instance_uuid'] for bmi in bm_list]

        # Create a list for the UI to use
        instance_list = []
        search_opts = {'all_tenants': True}
        for client, region in self.clients.get_clients():
            server_list = client.servers.list(search_opts=search_opts,
                                              limit=-1,
                                              detailed=True)

            # flavors tell us cpu/memory/disk allocated to the instance
            flavor_list = client.flavors.list(is_public=None, detailed=True)
            flavor_dict = {flavitem.id: flavitem for flavitem in flavor_list}
            image_list = client.images.list()
            image_dict = {imgitem.id: imgitem for imgitem in image_list}

            for nova_inst in server_list:
                # filter out any baremetal instances
                if nova_inst.id in bm_uuid_list:
                    continue
                instance = {}
                instance['name'] = nova_inst.name
                instance['status'] = nova_inst.status
                instance['host'] = nova_inst._info['OS-EXT-SRV-ATTR:host']
                instance['availability_zone'] = \
                    nova_inst._info['OS-EXT-AZ:availability_zone']
                instance['id'] = nova_inst.id

                try:
                    instance['image'] = image_dict[nova_inst.image['id']].name
                except:
                    # There are some instances tied to non-existent images
                    instance['image'] = 'UNKNOWN'

                instance['addresses'] = nova_inst.addresses
                instance['created'] = nova_inst.created
                powernum = nova_inst._info['OS-EXT-STS:power_state']
                instance['power_state'] = power_states.get(
                    powernum, "UNKNOWN[%d]" % powernum)

                # tasks states defined in nova/nova/compute/task_states.py
                instance['task_state'] = \
                    nova_inst._info['OS-EXT-STS:task_state']
                instance['key_name'] = nova_inst.key_name
                instance['metadata'] = nova_inst.metadata

                # get the project name.  If it's not found, just get the
                # tenant id instead
                instance['project'] = proj_dict.get(nova_inst.tenant_id,
                                                    nova_inst.tenant_id)
                instance['tenant_id'] = nova_inst.tenant_id
                instance['region'] = region

                try:
                    flavor = flavor_dict[nova_inst.flavor['id']]
                    instance['flavor'] = flavor.name
                    instance['cpu'] = {'vcpus': flavor.vcpus}
                    instance['memory'] = {'ram': flavor.ram}
                    instance['storage'] = {'disk': flavor.disk}
                except:
                    # There are some instances tied to flavors that don't
                    # appear to show up in flavor-list
                    instance['flavor'] = None
                    instance['cpu'] = None
                    instance['memory'] = None
                    instance['storage'] = None

                self._populate_metrics(instance)
                instance_list.append(instance)

        return {'instances': instance_list}

    def _populate_metrics(self, instance):
        monasca_metrics = self.request[api.DATA].get('monasca_metrics')
        if isinstance(monasca_metrics, list):
            instance['metrics'] = dict()
            for metric in monasca_metrics:
                req_data = \
                    dict(self.request[api.DATA].get('monasca_data'))
                req_data['name'] = metric
                monasca_dimensions = \
                    self.request[api.DATA].get('monasca_dimensions')
                if isinstance(monasca_dimensions, dict):
                    req_data['dimensions'] = dict()
                    for key, value in monasca_dimensions.iteritems():
                        # if dict its more complicated
                        if isinstance(value, dict):
                            instanceKey = value.get('property')
                            req_data['dimensions'][key] = \
                                instance[instanceKey]
                        else:
                            req_data['dimensions'][key] = value

                res = self.call_service(
                    target='monitor',
                    operation=req_data.get('operation', 'metric_statistics'),
                    data=req_data
                )
                instance['metrics'][metric] = res

    @service.expose('service-delete')
    def service_delete(self):
        """
        Delete the service which can be specified either by ``novaid`` or
        ``hostname``.

        Request format::

            "target": "nova",
            "operation": "service-delete",
            "novaid": "ID"
        """
        nova_id = self.data.get('novaid')
        host_name = self.data.get('hostname')

        if not nova_id and not host_name:
            raise Exception("Either novaid or hostname must be "
                            "populated")

        found = False
        for client, region in self.clients.get_clients():
            compute_list = client.services.list(binary="nova-compute")

            for instance in compute_list:
                if (nova_id and instance.id == nova_id) or \
                   (not nova_id and host_name == instance.host):

                    client.services.delete(instance.id)

                    # Also break out of the outer loop when the host is found
                    found = True
                    break

            if found:
                break

        if not found:
            raise Exception(self._("Could not find service to delete"))

        return self._(
            "Executed nova service delete on service {}").format(nova_id)

    @service.expose('instance-delete', is_long=True)
    def server_delete(self, validate):
        """
        Delete an instance.  This function will not return until nova has
        completed the deletion of the instance, which is to say, when nova
        no longer returns it in its list of servers.

        Request format::

            "target": "nova",
            "operation": "instance-delete",
            "instance_id": "ID"
        """
        inst_id = self.data['instance_id']
        if validate:

            for client, region in self.clients.get_clients():
                # TODO: Test that this doesn't throw an exception
                if client.servers.get(inst_id):
                    client.servers.delete(inst_id)
                    self.client_used_for_delete = client
                    break

            self.update_job_status('in progress', 25, task_id=inst_id)
            return self.SUGGESTED_POLL_INTERVAL
        else:
            # Now we call 'nova show' on that instance until it no longer
            # exists or something bad happens (keystone token times out,
            # nova has a problem, etc)
            while True:
                try:
                    self.client_used_for_delete.servers.get(inst_id)
                    sleep(self.SUGGESTED_POLL_INTERVAL)
                except NotFound:
                    # No longer see the instance, so we're good!
                    break

            self.response[api.DATA] = self._("instance {} deleted").format(
                inst_id)
            return self.response

    @classmethod
    def needs_services(cls):
        return ['compute']
