# (c) Copyright 2015-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

from cinderclient.v2 import client as cinderclient

from bll import api
from bll.common.util import get_conf
from bll.plugins import service


class CinderSvc(service.SvcBase):

    """
    This class deals with all the interaction with cinder client including
    cinder volume type creation and mapping the volume backends to volume
    types.

    The ``target`` value for this plugin is ``cinder``. See :ref:`rest-api`
    for a full description of the request and response formats.
    """
    def __init__(self, *args, **kwargs):
        """
        Initializer for the Cinder Client Service
        """
        super(CinderSvc, self).__init__(*args, **kwargs)

        self.cinder_client = cinderclient.Client(
            session=self.token_helper.get_session(),
            endpoint_type=get_conf("services.endpoint_type",
                                   default="internalURL"),
            user_agent=api.USER_AGENT)

    @service.expose(action="DELETE")
    def volume_type_delete(self):
        """
        Delete a volume type.

        Request format::

            "target": "cinder",
            "operation": "volume_type_delete",
            "action": "DELETE",
            "volume_type_id": "MYID"
        """
        vol_type = self.request[api.DATA]["volume_type_id"]
        response = self.cinder_client.volume_types.delete(vol_type)
        return response

    @service.expose(action="PUT")
    def volume_type_add(self):
        """
        Add a volume type with the given name.

        Request format::

            "target": "cinder",
            "operation": "volume_type_add",
            "action": "PUT",
            "volume_type": "MYTYPENAME"
        """
        vol_type = self.request[api.DATA]["volume_type"]
        volume_type = self.cinder_client.volume_types.create(vol_type)
        response = {'id': volume_type.id, 'name': volume_type.name}
        return response

    @service.expose()
    def volume_type_list(self):
        """
        Return a list of volume types.

        Request format::

            "target": "cinder",
            "operation": "volume_type_list"
        """
        volume_types = self.cinder_client.volume_types.list()
        return {v.id: v.name for v in volume_types}

    @service.expose(action="PUT")
    def map_volume_backend(self):
        """
        Updates the ``volume_backend_name`` extra specs of a volume type to
        refer to the given backend name.

        Request format::

            "target": "cinder",
            "operation": "volume_type_list",
            "volume_type_id": "MYID",
            "backend_name": "MYBACKEND"
        """
        vol_type_id = self.request[api.DATA]["volume_type_id"]
        backend_name = self.request[api.DATA]["backend_name"]

        response = {}
        volume_type = self.cinder_client.volume_types.get(vol_type_id)
        resp = volume_type.set_keys({"volume_backend_name": backend_name})
        response[vol_type_id] = resp
        return response

    @classmethod
    def needs_services(cls):
        return ['volume']
