# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from bll import api
from bll.plugins import service
from ironicclient import client as ironic_client
from bll.plugins.region_client import RegionClient
from bll.common.util import get_conf


class IronicSvc(service.SvcBase):
    """
    The ``target`` value for this plugin is ``ironic``. See :ref:`rest-api`
    for a full description of the request and response formats.

    This really should be called the baremetal service, but unfortunately,
    there is already one with that name containing services that really
    belong in eon_service.
    """

    def __init__(self, *args, **kwargs):
        super(IronicSvc, self).__init__(*args, **kwargs)

        self.clients = RegionClient('baremetal', self._get_ironic_client,
                                    self.token, self.region)

    def _get_ironic_client(self, region=None, url=None, **kwargs):
        return ironic_client.get_client(
            1,
            os_auth_token=self.token,
            ironic_url=url,
            os_region_name=region,
            user_agent=api.USER_AGENT,
            insecure=get_conf("insecure"))

    @service.expose('node.list')
    def list_nodes(self):
        """
        Request format::

            "target": "ironic",
            "operation": "node.list"

        :return:
        List of nodes from the ironic service
        """

        nodelist = []
        for client, region in self.clients.get_clients():
            for node in client.node.list():
                nodelist.append(node.to_dict())

        return nodelist

    @service.expose('node.get')
    def get_node(self):
        """
        Get details for a specific node.

        Request format::

            "target": "ironic",
            "operation": "node.get",
            "node_id": "MYNODEID"

        """

        for client, region in self.clients.get_clients():
            node = client.node.get(node_id=self.data['node_id'])
            if node:
                return node.to_dict()

    @service.expose('baremetal-list')
    def baremetal_list(self):
        """
        Return a list of nodes from nova and ironic.  Details are return
        from both nova and ironic only for baremetal instances.

        Request format::

            "target": "ironic",
            "operation": "baremetal-list"

        """
        inst_list = self.call_service(target='nova',
                                      operation='instance-list',
                                      data={'show_baremetal': True},
                                      region=self.region
                                      )['instances']
        inst_dict = {item['id']: item for item in inst_list}

        agg_list = []
        for node in self.list_nodes():
            details = {
                'baremetal': node,
                'compute': inst_dict.get(node['instance_uuid'])
            }
            agg_list.append(details)

        return agg_list

    @service.expose('node.delete')
    def delete_node(self):
        """
        Deletes a node from ironic.

        Request format::

            "target": "ironic",
            "operation": "node.delete",
            "node_id": "MYNODEID"

        :returns:
        ``None`` when the operation completes successfully
        """
        for client, region in self.clients.get_clients():
            client.node.delete(node_id=self.data['node_id'])

    @classmethod
    def needs_services(cls):
        return ['baremetal']
