# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

import logging
import time

from eonclient import client as eonclient
from bll import api
from bll.common.util import get_conf, is_stdcfg
from bll.plugins import service
from bll.plugins.region_client import RegionClient


ENDPOINT_TYPE = u"esx_onboarder"
DEFAULT_SERVER_GROUP = "RACK1"

LOG = logging.getLogger(__name__)


class EONSvc(service.SvcBase):

    """
    Provide functionality to handle all eon-related operations. Used for
    compute node activation, deactivation, delete and list.

    The ``target`` value for this plugin is ``eon``. See :ref:`rest-api`
    for a full description of the request and response formats.
    """
    REQ_POLL_INT = 10

    def __init__(self, *args, **kwargs):
        super(EONSvc, self).__init__(*args, **kwargs)

        self.data = self.request.get(api.DATA)
        self.datadata = self.data.get(api.DATA)

        self.clients = RegionClient(ENDPOINT_TYPE, self._get_eon_client,
                                    self.token, self.region)

        self.eon_client, _region = self.clients.get_client()

    def _get_eon_client(self, region=None, url=None):
        return eonclient.get_client('2', os_token=self.token, eon_url=url,
                                    user_agent=api.USER_AGENT,
                                    insecure=get_conf("insecure"))

    @service.expose()
    def prepare_activate_template(self):
        """
        Returns an activation template for the given host type using data
        from the ardana service.

        Request format::

            "target": "eon",
            "operation": "prepare_activate_template"
        """
        type = self.datadata.get('type')

        if type == 'esxcluster':

            all_network_names = self.call_service(
                target="ardana",
                operation="do_path_operation",
                data={"path": "model/entities/networks"})

            all_network_group_names = self.call_service(
                target="ardana",
                operation="do_path_operation",
                data={"path": "model/entities/network-groups"})

            filtered_network_groups = []
            for nw_group in all_network_group_names:
                if nw_group.get("tags") and isinstance(nw_group["tags"], list):
                    for tag in nw_group['tags']:
                        if isinstance(tag, dict):
                            if 'neutron.networks.vxlan' in tag.keys() or \
                                    'neutron.networks.vlan' in tag.keys():
                                filtered_network_groups.append(nw_group.get(
                                    'name'))
                        elif isinstance(tag, str):
                            if tag in ['neutron.networks.vlan',
                                       'neutron.networks.vxlan']:
                                filtered_network_groups.append(nw_group.get(
                                    'name'))

            cloud_trunk_count = 0
            filtered_network_names = []
            for network in all_network_names:
                if network.get('network-group') in filtered_network_groups:
                    cloud_trunk_count += 1
                    filtered_network_names.append(network)

            return {
                "cloud_trunk": cloud_trunk_count,
                "mgmt_trunk": 1,
                "server_groups": [],
                "network_names": filtered_network_names
            }
        elif type in ['hyperv', 'hlinux', 'rhel']:

            control_planes = self.call_service(
                target="ardana",
                operation="do_path_operation",
                data={"path": "model/entities/control-planes"})

            server_roles_filters = []
            if type in ['hlinux', 'rhel']:
                server_roles_filters.append('nova-compute-kvm')
            elif type == 'hyperv':
                server_roles_filters.append('nova-compute-hyperv')

            server_roles = []
            for plane in control_planes:
                for resource in plane.get('resources'):
                    for component in resource.get('service-components'):
                        if component in server_roles_filters:
                            server_roles.append(resource)

            all_server_groups = self.call_service(
                target="ardana",
                operation="do_path_operation",
                data={"path": "model/entities/server-groups"})

            server_groups = []
            for server_group in all_server_groups:
                has_srv_grp = server_group.get("server-groups", None)
                if not has_srv_grp:
                    server_groups.append(server_group)

            response = {
                "server_roles": server_roles,
                "server_groups": server_groups
            }

            if type != 'hyperv':
                nic_mappings = self.call_service(
                    target="ardana",
                    operation="do_path_operation",
                    data={"path": "model/entities/nic-mappings"})
                response['nic_mappings'] = nic_mappings

            return response

        raise Exception(self._("Invalid Resource Type Specified"))

    def _validate_resource_state(self, id, in_progress_states, error_states):
        eonsvc_response = self.eon_client.get_resource(id)
        while eonsvc_response['state'] in in_progress_states:
            time.sleep(self.REQ_POLL_INT)
            eonsvc_response = self.eon_client.get_resource(id)
            self.update_job_status(msg=eonsvc_response, percentage_complete=10)

        if eonsvc_response['state'] in error_states:
            self.response.error(
                self._("Activation Failed for Resource with {0},{1}").format(
                    eonsvc_response.get('id', ''),
                    eonsvc_response.get('name', '')))

    @service.expose(is_long=True)
    def deactivate_resource(self, validate):
        """
        Deactivates one or more resources from eon in a long-running
        operation.

        This function uses a very strange and counter-intuitive request
        format::

            "target": "eon",
            "operation": "deactivate_resource",
            "ids" : {
                "MYID1": "True",
                "MYID2": "False",
                ...
                "MYIDN": "False",
            }

        The value of each item in the dictionary, "True" or "False",
        will indicate whether the ``forced`` option will be used when calling
        eon's ``deactivate_resource`` for that id.
        """
        if validate:
            self.response[api.DATA] = {'ids': self.datadata.get('ids')}
            return self.REQ_POLL_INT

        ids = self.datadata['ids']
        for id, forced_str in ids.iteritems():
            try:
                data = {"forced": forced_str.lower() != "false"}
                self.eon_client.deactivate_resource(id, data)
                eonsvc_response = self.eon_client.get_resource(id)
                while eonsvc_response['state'] in ["deactivating"]:
                    time.sleep(self.REQ_POLL_INT)
                    eonsvc_response = self.eon_client.get_resource(id)
                    self.response[api.DATA]['ids'].\
                        update({id: {api.STATUS: api.STATUS_INPROGRESS}})
                    self.update_job_status(percentage_complete=10)

                self.response[api.DATA]['ids'].update({id: {api.STATUS:
                                                            api.COMPLETE}})

            except Exception as e:
                message = {"ID:" + id + " failed with "  "reason " +
                           e.details}
                LOG.exception(message)
                self.response[api.DATA]['ids'].update({id: {api.STATUS:
                                                            api.STATUS_ERROR}})

        return self.response

    @service.expose(is_long=True)
    def activate_resource(self, validate):
        """
        Activates a resource using eon's ``activate_resource`` API in a
        long-running operation.

        Request format::

            "target": "eon",
            "operation": "activate_resource",
            "data" : { "data" : {
                "id": "MYID",
                "type": "MYTYPE",
                "network_config": ...
                ...
            }

        """

        if validate:
            self.response[api.DATA] = {'id': self.datadata.get('id'),
                                       'state': 'activating'}
            return self.REQ_POLL_INT

        type_resource = self.datadata.get('type', '')
        id = self.datadata.get('id', '')
        network_config = self.datadata.get('network_config')
        self.response[api.DATA] = {'id': id, 'state': 'activating'}
        self.update_job_status(percentage_complete=10)
        if id and type_resource == 'esxcluster' and network_config:
            mgmt_trunk = network_config.get("mgmt_trunk", [])
            if mgmt_trunk and len(mgmt_trunk) > 0:
                network_config['mgmt_trunk'] = network_config[
                    'mgmt_trunk'][0]
                if network_config['mgmt_trunk'].get('server_group', None):
                    del network_config['mgmt_trunk']['server_group']
                activation_template = self.eon_client. \
                    get_resource_template(type_resource, network_config)
                input_model = activation_template.get('input_model', None)
                if input_model:
                    # TODO: EON needs server group as RACK1 as of now
                    activation_template['input_model']['server_group'] \
                        = DEFAULT_SERVER_GROUP
                self.update_job_status(percentage_complete=20)
                self.eon_client.activate_resource(id, activation_template)
                self._validate_resource_state(id, ["activating",
                                                   "provisioning",
                                                   "provision-initiated"],
                                              ["provisioned", "imported"])

        elif id != '' and type_resource in ["hlinux", "rhel", "hyperv"] \
                and network_config:
            if bool(self.datadata.get("is_modified")):
                self.eon_client.update_resource(id, self.datadata.get(
                    'resource'))
            activation_template = self.eon_client.\
                get_resource_template(type_resource, {})
            self.update_job_status(percentage_complete=20)
            # Fix for defect: OPSCON-1279
            if type_resource == "rhel":
                if self.datadata.get("run_disk_config") == "True":
                    activation_template["skip_disk_config"] = False
                else:
                    activation_template["skip_disk_config"] = True
                if self.datadata.get("run_wipe_disks") == "True":
                    activation_template["run_wipe_disks"] = True
                else:
                    activation_template["run_wipe_disks"] = False
            input_model = activation_template.get('input_model', None)
            if not input_model:
                raise Exception(self._(
                    "Could not get Activation Template from EON"))

            input_model['nic_mappings'] = network_config.get(
                'nic_mappings', "")
            input_model['server_group'] = \
                network_config.get('server_group', "")
            input_model['server_role'] = \
                network_config.get('server_role', "")
            activation_template['input_model'] = input_model
            self.eon_client.activate_resource(id, activation_template)
            self._validate_resource_state(id, ["activating", "provisioning"],
                                          ["provisioned"])
        else:
            raise Exception(self._("Invalid Resource Type Specified or "
                            "Empty/Invalid Network Configuration was sent"))

        return self.response

    @service.expose()
    def resource_list(self):
        """
        Returns a list of resources known to eon.

        Request format::

            "target": "eon",
            "operation": "resource_list",
            "type": "TYPE",
            "state": "STATE"
        """

        resource_type = self.data.get('type')
        resource_state = self.data.get('state')

        result_list = []
        for client, region in self.clients.get_clients():

            resource_list = client.get_resource_list(resource_type,
                                                     resource_state)
            for resource in resource_list:
                resource['region'] = region
                result_list.append(resource)

        return result_list

    @service.expose()
    def resource_get(self):
        """
        Returns a details of a resource from eon.

        Request format::

            "target": "eon",
            "operation": "resource_get",
            "id": "MYID"
        """

        for client, region in self.clients.get_clients():
            try:
                resource = client.get_resource(self.data['id'])
                resource['region'] = region
                return resource
            except Exception:
                pass

        raise Exception(self._("Resource not found in eon"))

    @service.expose()
    def register_compute(self):
        """
        Register a compute resource with eon.

        Request format::

            "target": "eon",
            "operation": "resource_compute",
            "name": "MYNAME",
            "ip_address": "MYIP",
            "type": "MYTYPE",
            "username": "MYUSER",
            "password": "MYPASS",
            "port": "MYPORT"
        """
        resource_host_data = {
            "name": self.datadata['name'],
            "ip_address": self.datadata['ip_address'],
            "type": self.datadata['type'],
            "username": self.datadata['username'],
            "password": self.datadata['password'],
            "port": self.datadata['port']
            }
        return self.eon_client.add_resource(resource_host_data)

    @service.expose()
    def delete_resource(self):
        """
        Delete one ore more compute resources from eon.

        Request format::

            "target": "eon",
            "operation": "delete_resource",
            "data": {"data": {"ids": ["MYID1", "MYID2"...]}}
        """
        if is_stdcfg():
            return self.eon_client.delete_resource(self.datadata['id'])
        else:
            datadata = self.data.get(api.DATA)
            self.response[api.DATA] = []
            ids = datadata['ids']
            for id in ids:
                try:
                    self.eon_client.delete_resource(id)
                    self.response[api.DATA].append({api.STATUS: api.COMPLETE})
                except Exception as e:
                    self.response[api.DATA].append(
                        {api.STATUS: api.STATUS_ERROR,
                         api.DATA: e.message})
            return self.response

    @service.expose()
    def get_resource_mgr(self):
        """
        Returns the eon resource manager with the given id.

        Request format::

            "target": "eon",
            "operation": "get_resource_mgr",
            "id": "MYID"
        """
        return self.eon_client.get_resource_mgr(self.data['id'])

    @classmethod
    def needs_services(cls):
        return [ENDPOINT_TYPE, "ardana"]
