# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

from bll import api
from bll.common.util import get_conf
from bll.plugins import service
from bll.plugins.service import SvcBase
from eonclient import client as eon_client
import time

ENDPOINT_TYPE = u"esx_onboarder"
REQ_POLL_INT = 10


class BaremetalSvc(SvcBase):
    """
    The ``target`` value for this plugin is ``baremetal``. See :ref:`rest-api`
    for a full description of the request and response formats.
    """

    def __init__(self, *args, **kwargs):
        super(BaremetalSvc, self).__init__(*args, **kwargs)
        self.eon_client = self._get_eon_client()

    def _get_eon_client(self):
        eon_endpoint = self.token_helper.get_service_endpoint(ENDPOINT_TYPE)
        return eon_client.get_client('2',
                                     os_token=self.token,
                                     eon_url=eon_endpoint,
                                     insecure=get_conf("insecure"),
                                     user_agent=api.USER_AGENT)

    @service.expose()
    def list_baremetal(self):
        """
        Obtains a list of baremetal servers from eon that are either in the
        ``provisioning`` or ``imported`` state.  It excludes those server
        that are already configured as hypervisors.

        Request format::

            "target": "baremetal",
            "operation": "list_baremetal"
        """
        baremetal_list = []
        resp = self.eon_client.get_resource_list()
        for resource in resp:
            if (resource['type'] not in ['esxcluster', 'kvm', 'hyperv']):
                if (resource['state'] in ['provisioning', 'imported']):
                    baremetal_list.append(resource)
        return baremetal_list

    @service.expose(action='POST')
    def register_baremetal(self):
        """
        Registers a baremetal server with eon.

        Request format::

            "target": "baremetal",
            "action": "POST",
            "operation": "register_baremetal"
            "name": "MYNAME",
            "mac_addr": "MYADDR",
            ...
        """
        try:
            req_data = self.data[api.DATA]
            baremetal_data = self._get_baremetal_data(req_data)
            self.eon_client.add_resource(baremetal_data)
            self.response[api.DATA] = self._(
                "Baremetal registered successfully")
            self.response.complete()
        except Exception as e:
            self.response.error(e.details)

    @service.expose(action='DELETE')
    def unregister_baremetal(self):
        """
        Unregisters one or more baremetal servers from eon.

        Request format::

            "target": "baremetal",
            "action": "DELETE",
            "operation": "unregister_baremetal"
            "data" : { "data" : { "ids" : [ "MYID1", "MYID2" ] } }
        """
        list_data = self.request[api.DATA][api.DATA]['ids']
        resp_dict = {}
        for id in list_data:
            temp = self._unregister_from_eon(id)
            resp_dict[id] = temp
        return resp_dict

    def _unregister_from_eon(self, id):
        try:
            resp = {}
            res, data = self.eon_client.delete_resource(id)
            resp[api.DATA] = self._("Baremetal unregistered successfully")
            resp[api.STATUS] = api.COMPLETE
        except Exception as e:
            resp[api.STATUS] = api.STATUS_ERROR
            if hasattr(e, "details"):
                resp[api.DATA] = e.details
            else:
                resp[api.DATA] = e.message
        return resp

    def update_job_status(self, percentage_complete=0):
        self.response[api.PROGRESS] = {
            api.PERCENT_COMPLETE: percentage_complete}
        self.put_resource(self.request[api.TXN_ID], self.response)

    @service.expose(action='POST', is_long=True)
    def provision_baremetal(self):
        """
        Provisions a baremetal server with eon.  This is a long-running
        operation.

        Request format::

            "target": "baremetal",
            "action": "POST",
            "operation": "provision_baremetal"
            "name": "MYNAME",
            "mac_addr": "MYADDR",
            ...
        """
        req_data = self.data[api.DATA]
        is_auto_provision_enabled = False
        if req_data['auto_provision']:
            is_auto_provision_enabled = not(req_data['auto_provision'] ==
                                            'False')
        baremetal_id = None
        self.update_job_status(percentage_complete=10)
        try:
            if is_auto_provision_enabled:
                baremetal_data = self._get_baremetal_data(req_data)
                resp = self.eon_client.add_resource(baremetal_data)
                baremetal_id = resp['id']
            else:
                baremetal_id = req_data['id']
                update_baremetal_data = {"username": req_data['username'],
                                         "password": req_data['password']}
                resp = self.eon_client.update_resource(baremetal_id,
                                                       update_baremetal_data)
            baremetal_data_req = {}
            baremetal_data_req['type'] = req_data['os_type']
            if req_data['os_type'] == 'rhel':
                baremetal_data_req['os_version'] = 'rhel72'
            if req_data['boot_from_san'] == 'True':
                baremetal_data_req['boot_from_san'] = 'yes'
            baremetal_data = self.eon_client.provision_resource(
                baremetal_id, baremetal_data_req)
            # Poll/wait while provisioning is underway
            while (baremetal_data['state'] != 'provisioned' and
                   baremetal_data['state'] != 'imported'):
                time.sleep(REQ_POLL_INT)
                baremetal_data = self.eon_client.get_resource(baremetal_id)
                # Invoke the baremetal resource self._list_baremetal()
            if (baremetal_data['state'] == 'provisioned' and
                    baremetal_data['state'] != 'imported'):
                self.response[api.STATUS] = api.COMPLETE
                self.response[api.DATA] = self._(
                    "Baremetal provisioned successfully")
            else:
                self.response.error(self._("Provisioning baremetal failed"))
        except Exception as e:
            self.response.error(e.details)
        return self.response

    @service.expose(action='PUT')
    def update_baremetal(self):
        """
        Updates a baremetal server with eon.  This is a long-running
        operation.

        Request format::

            "target": "baremetal",
            "action": "POST",
            "operation": "update_baremetal"
            "id": "MYID",
            "name": "MYNAME",
            "mac_addr": "MYADDR",
            ...
        """
        try:
            req_data = self.data[api.DATA]
            baremetal_id = req_data['id']
            baremetal_data = self._get_baremetal_data(req_data)
            if baremetal_data['type']:
                del baremetal_data['type']
            resp, data = self.eon_client.update_resource(baremetal_id,
                                                         baremetal_data)
            self.response[api.DATA] = self._("Baremetal updated successfully")
            self.response.complete()
        except Exception as e:
            self.response.error(e.details)

    def _get_baremetal_data(self, req_data):
        data = {"name": req_data["name"],
                "ilo_ip": req_data["ilo_ip"],
                "type": "baremetal",
                "mac_addr": req_data["mac_addr"],
                "ilo_user": req_data["ilo_user"],
                "ilo_password": req_data["ilo_password"],
                "ip_address": req_data["ip_address"],
                "port": req_data["port"]
                }
        if "username" in req_data:
            data["username"] = req_data["username"]
        if "password" in req_data:
            data["password"] = req_data["password"]
        if "os_type" in req_data:
            data["os_type"] = req_data["os_type"]
        return data

    @classmethod
    def needs_services(cls):
        return ['esx_onboarder']
