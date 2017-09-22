# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

import logging
import time

from bll import api
from bll.common.exception import InvalidBllRequestException
from bll.common.util import get_conf
from bll.plugins.service import SvcBase, expose

LOG = logging.getLogger(__name__)

EON_ENDPOINT_TYPE = u"esx_onboarder"

# WARNING: This caching mechanism does not work correctly in an HA environment.
#          It should be fixed or removed.
# An internal cache for vCenter States.
# This maintains the in progress states for vCenter.
# The possible states are registering, updating, unregistering.
# The entries will be removed when the vcenter's reaches the stable state.
# ie, registered, unregistered and updated.
VCENTER_STATES = {}
REGISTERING_STATE = "Registering"
UNREGISTERING_STATE = "Unregistering"
UPDATING_STATE = "Updating"
REGISTERED_STATE = "Registered"


def update_vcenter_cache(vcenter_id, state):
    VCENTER_STATES[vcenter_id] = state


def get_vcenter_state(vcenter_id):
    return VCENTER_STATES.get(vcenter_id, REGISTERED_STATE)


def remove_vcenter_cache(vcenter_id):
    return VCENTER_STATES.pop(vcenter_id, None)


class IntegratedToolsSvc(SvcBase):
    """
    This service represents the composite service for Integrated Tools.

    The ``target`` value for this plugin is ``vcenters``. See :ref:`rest-api`
    for a full description of the request and response formats.
    """

    def __init__(self, *args, **kwargs):
        super(IntegratedToolsSvc, self).__init__(*args, **kwargs)
        self.eon_client = self._get_eon_client()

    def _get_eon_client(self):
        eon_url = self.token_helper.get_service_endpoint(EON_ENDPOINT_TYPE)
        if not eon_url:
            return

        try:
            # This import cannot be at the top of this file, or it makes
            # the whole file dependent on the presence of eon, but eon is
            # supposed to be optional for this service
            from eonclient import client as eon_client
            return eon_client.get_client('2', os_token=self.token,
                                         eon_url=eon_url,
                                         user_agent=api.USER_AGENT,
                                         insecure=get_conf("insecure"))
        except ImportError:
            pass

    @expose(operation='vcenters', action='GET')
    def get_vcenter_resource_list(self):
        """
        Request format::

            "target": "vcenters",
            "action": "GET",
            "operation": "vcenters"

        :return: List of vcenters managers from eon
        """
        vcenters = []
        if self.eon_client:
            resouce_mgr_list = self.eon_client.get_resource_mgr_list()
            vcenters = [src
                        for src in resouce_mgr_list
                        if src['type'] == 'vcenter']

            resource_list = self.eon_client.get_resource_list()
            clusters = [mem
                        for mem in resource_list
                        if mem['type'] == 'esxcluster']

            for vcenter in vcenters:
                vcenter['state'] = get_vcenter_state(vcenter['id'])

                activated_clusters = 0
                for cluster in clusters:
                    if vcenter.get('id') == cluster.get('resource_mgr_id') \
                            and cluster.get('state') in ('activated',
                                                         'provisioned'):
                            activated_clusters += 1
                vcenter['activated_clusters'] = activated_clusters

        return vcenters

    @expose('count_vcenters')
    def get_vcenters_count(self):
        """
        Request format::

            "target": "vcenters",
            "operation": "count_vcenters"

        :return: Count of resource managers from eon
        """
        return len(self.get_vcenter_resource_list())

    @expose(operation='vcenters', action='POST', is_long=True)
    def register_vcenter(self, validate):
        """
        Register vcenter

        Request format::

            "target": "vcenters",
            "operation": "vcenters",
            "action": "POST",
            "data": {
                "data" : {
                    "name": "vcenter1",
                    "username": "bob",
                    "password": "pass",
                    "ip_address": "192.168.10.40",
                    "port": "443",
                    "description": "My vcenter",
                    "type": "vcenter"
                }
            }
        """
        if validate:
            return

        datadata = self.data[api.DATA]

        vcenter_id = None

        try:
            if self.eon_client:
                eonsvc_response = self.eon_client.add_resource_mgr(datadata)
                self.update_job_status(percentage_complete=30)
                vcenter_id = eonsvc_response['id']

                update_vcenter_cache(vcenter_id, REGISTERING_STATE)

            return self.response

        except Exception as e:
            message = self._("vCenter registration failed: {}").format(e)
            raise Exception(message)

        finally:
            remove_vcenter_cache(vcenter_id)

    @expose(operation='edit_vcenter', action='PUT', is_long=True)
    def edit_vcenter(self, validate):
        """
        Edit the vCenter in eon

        Request format::

            "target": "vcenters",
            "action": "PUT",
            "operation": "edit_vcenter",
            "data": {
                "data" : {
                    "id": "39587235",
                    "name": "vcenter1",
                    "username": "bob",
                    "password": "pass",
                    "ip_address": "192.168.10.40"
                }
            }
        """
        datadata = self.data[api.DATA]

        if validate:
            if not datadata or 'id' not in datadata:
                raise InvalidBllRequestException(
                    self._("Invalid or incomplete vCenter id passed"))

            if self.eon_client:
                eon_vcenter = self.eon_client.get_resource_mgr(datadata['id'])
                if not eon_vcenter:
                    raise InvalidBllRequestException(
                        self._("vCenter is not registered"))
            return

        vcenter_id = datadata.pop('id')

        update_vcenter_cache(vcenter_id, UPDATING_STATE)

        # Remove type if present
        datadata.pop('type', None)

        eon_updated = False
        try:
            if self.eon_client:
                self.eon_client.update_resource_mgr(vcenter_id, datadata)
                eon_response = self.eon_client.get_resource_mgr(vcenter_id)
                while eon_response['meta_data'][0]['value'] == "updating":
                    time.sleep(10)
                    eon_response = self.eon_client.get_resource_mgr(
                        vcenter_id)
                    self.update_job_status(percentage_complete=10)
                self.update_job_status(percentage_complete=50)
                eon_updated = True

                self.update_job_status(percentage_complete=75)

            return self.response

        except Exception as e:
            if eon_updated:
                raise Exception(self._("{0}. vCenter {1} is partially "
                                       "updated").format(e, datadata['name']))
            raise e

        finally:
            remove_vcenter_cache(vcenter_id)

    @expose(operation='vcenters', action='DELETE', is_long=True)
    def unregister_vcenters(self):
        """
        Deletes the vcenter from EON service

        This service expects to receive dictionary named ids that contains
        entries that map ids to corresponding names.  For example::

            "target": "vcenters",
            "action": "DELETE",
            "operation": "vcenters",
            "ids": {
                "id1": "Vcenter 1",
                "id2": "Vcenter 2"
            }

        Since several vcenters can be unregistered in a single call,
        the response data from this call is a list of responses, one per
        each id.
        """

        # This wrapper logic calls _unregister_single_vcenter for each vcenter
        # whose ID is given and gathers its results into one big return list.
        # It would be preferable to do this looping in the UI.

        response_list = []
        for vcenter_id, vcenter_name in self.data['ids'].iteritems():

            result = {
                'id': vcenter_id,
                'name': vcenter_name,
            }
            try:
                result[api.DATA] = self._unregister_single_vcenter(vcenter_id)
                result[api.STATUS] = api.COMPLETE

            except Exception as e:
                result[api.DATA] = str(e)
                result[api.STATUS] = api.STATUS_ERROR

            response_list.append(result)

        return response_list

    def _unregister_single_vcenter(self, vcenter_id):
        """
        Unregisters a single vcenter.
        """
        update_vcenter_cache(vcenter_id, UNREGISTERING_STATE)

        try:
            if self.eon_client:
                self.eon_client.get_resource_mgr(vcenter_id)
                self.eon_client.delete_resource_mgr(vcenter_id)
        finally:
            remove_vcenter_cache(vcenter_id)

    # For the catalog service, this method indicates whether this plugin
    #    is available for use by the UI.  It is considered available if
    #    the EON service is available.
    @classmethod
    def is_available(cls, available_services):

        return 'esx_onboarder' in available_services
