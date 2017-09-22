# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from bll import api
from bll.common.util import get_conf
from bll.plugins.service import expose, SvcBase
from bll.common.exception import InvalidBllRequestException

import logging
import requests
import json
import time

LOG = logging.getLogger(__name__)


class ArdSvc(SvcBase):
    """
    The ardana service is written does not have a python client, since it is
    written in JavaScript and runs under node.  Therefore all interaction is
    done via direct REST calls

    The ``target`` value for this plugin is ``ardana``. See :ref:`rest-api`
    for a full description of the request and response formats.
    """

    TASK_POLL_INTERVAL = 10

    def __init__(self, *args, **kwargs):
        super(ArdSvc, self).__init__(*args, **kwargs)

        url = self.token_helper.get_service_endpoint('ardana')
        self.base_url = "/".join([url.strip(), 'api/v1'])

        if not self.operation:
            self.operation = 'do_path_operation'

    @expose()
    def delete_compute_host(self):
        """
        Delete a host

        Once the delete operation successfully completes
        ensure that nova-service delete call is made.
        This will be removed as soon as the delete host playbook is created,
        (which will be called from the ardana backend)

        Request format::

            "target": "ardana",
            "operation": "delete_compute_host",
            "data": {
                "request_data": {
                    "serverid": "MYID",
                    "novaServiceDelete": {
                        "hostname": "MYHOSTNAME"
                    },
                    ...
                }
            }

        """

        # Ensure we have the required properties to start with
        request_data = self.data[api.REQUEST_DATA]
        serverid = request_data['serverid']
        hostname = request_data['novaServiceDelete']['hostname']

        # Make the usual ardana delete request to /server
        url = 'servers/%s/process' % serverid
        self._request(url, action='DELETE')

        # Successfully removed the server from the model and updated config
        # processor output. Need now to ensure compute host is deleted from
        # the nova world
        return self.call_service(target="nova",
                                 operation="service-delete",
                                 data={'hostname': hostname})

    @expose()
    def do_path_operation(self):
        """
        Perform an operation against the given path in ardana_service.
        Example payload (``request_data`` and ``request_parameters`` sections
        are optional)::

            "target": "ardana",
            "operation": "do_path_operation",
            "data": {
                "path": "model/entities/server",
                "request_data": {                              # OPTIONAL
                    "limit": "MYLIMIT",
                    "encryptionKey": "MYKEY"
                },
                "request_parameters": [ "MYKEY=MYVALUE", ...]  # OPTIONAL
            }
        """

        # Convert list of key=value strings into a dictionary, .e.g.
        # [ "key1=value1", "key2=value2" ] =>
        #   { 'key1': "value1", "key2": "value2" }
        query_parms = None
        if api.REQUEST_PARAMETERS in self.data:
            parms_list = self.data[api.REQUEST_PARAMETERS]
            query_parms = dict([x.split('=') for x in parms_list])

        return self._request(self.data[api.PATH],
                             query_parms,
                             self.data.get(api.REQUEST_DATA),
                             action=self.action or 'GET')

    @expose()
    def get_network_data(self):
        """
        Aggregates the networking information in the servers list to return
        a list of networks across all servers.  Example payload:

            "target": "ardana",
            "operation": "get_network_data"

        """
        server_info = self._request('model/cp_output/server_info_yml')

        agg_networks = {}
        for host_data in server_info.values():
            for networks in host_data['net_data'].values():
                for network_name in networks:
                    if network_name not in agg_networks:
                        agg_networks[network_name] = networks[network_name]

        # optionally, remove host-specific/unimportant data from each network
        for network_data in agg_networks.values():
            for unwanted_key in ['addr', 'endpoints']:
                network_data.pop(unwanted_key, None)

        return agg_networks.values()

    @expose(is_long=True)
    def run_playbook(self, validate):
        """
        Performs an ansible playbook operation.

        Request format::

            "target": "ardana",
            "operation": "run_playbook",
            "data": {
                "playbook_name": "MYPLAYBOOK",    # REQUIRED
                "playbook_PARAM1": "MYVALUE",     # OPTIONAL
                ...
            }
        """

        if validate:
            playbook_name = self.data.pop('playbook_name', None)
            if not playbook_name:
                raise InvalidBllRequestException('unspecified playbook '
                                                 'to run')

            # Initiate the request and get its reference
            req_path = 'playbooks/' + playbook_name
            resp = self._request(req_path,
                                 body=self.data,
                                 action='POST')
            self.ref_id = resp['pRef']
            self.status_path = 'plays/' + self.ref_id
            self.update_job_status(resp, 25)
            return
        else:
            still_alive = True
            try:
                while still_alive:
                    poll_resp = self._request(self.status_path)
                    still_alive = poll_resp.get('alive', False)
                    if still_alive:
                        self.update_job_status(poll_resp, 50)
                        time.sleep(self.TASK_POLL_INTERVAL)
                    # We have no idea how long a playbook is going to take
                return poll_resp
            except Exception as e:
                LOG.exception(e)
                self.response.error(self._(
                    'Unknown error occurred, please refer to the following '
                    'ardana log: {}').format(self.ref_id))
                return self.response

    def _request(self, relative_path, query_params=None, body=None,
                 action='GET'):

        url = "/".join([self.base_url, relative_path.strip('/')])

        if isinstance(body, dict):
            body = json.dumps(body)

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Auth-Token': self.token,
            'User-Agent': api.USER_AGENT
        }

        response = requests.request(action,
                                    url,
                                    params=query_params,
                                    data=body,
                                    headers=headers,
                                    verify=not get_conf("insecure"))

        if 400 <= response.status_code < 600:
            # Raise an exception if not found. The content has the error
            # message to return
            try:
                message = response.json()['message']
            except Exception:
                message = response.content
            raise Exception(message)
        return response.json()

    @classmethod
    def needs_services(cls):
        return ['ardana']
