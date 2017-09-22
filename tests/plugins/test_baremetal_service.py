# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

import unittest
from bll import api
from bll.api.request import BllRequest
from bll.api.auth_token import TokenHelpers
from tests.util import get_mock_token
from mock import patch
from bll.plugins.baremetal_service import BaremetalSvc

baremetal_data = {"name": "Datacenter-1",
                  "mac_addr": "52:54:00:63:a5:0a",
                  "ip_address": "12.1.1.1",
                  "ilo_ip": "12.2.1.1",
                  "ilo_user": "Administrator",
                  "ilo_password": "password",
                  "type": "baremetal",
                  "username": "stack",
                  "password": "stack",
                  "port": "1234",
                  "id": "1"
                  }


class EonClientBaremetal():
    def get_resource_list(self):
        return [{"state": "imported", "name": "MyBaremetal",
                 "type": "hlinux"}]

    def add_resource(self, baremetal_data):
        return {"id": "12234",
                "name:": "MyBaremetal"}

    def delete_resource(self, id):
        return (id, id)

    def provision_resource(self, baremetal_id, baremetal_data_req):
        return {"state": "provisioned"}


class TestBaremetal(unittest.TestCase):
    @patch.object(BaremetalSvc, '_get_eon_client')
    @patch.object(TokenHelpers, 'get_service_endpoint')
    @patch.object(TokenHelpers, 'get_token_for_project')
    def test_list_baremetal(self, mock_get_token_for_project,
                            mock_get_service_endpoint, mock_client):
        mock_get_token_for_project.return_value = "admin"
        mock_get_service_endpoint.return_value = "http://localhost:8070/v2.0"
        eonclient_obj = EonClientBaremetal()
        mock_client.return_value = eonclient_obj
        request = {
            api.TARGET: 'baremetal',
            api.AUTH_TOKEN: get_mock_token(),
            api.ACTION: 'GET',
            api.DATA: {
                api.OPERATION: 'list_baremetal',
            }
        }
        svc = BaremetalSvc(bll_request=BllRequest(request))
        output = svc.list_baremetal()
        self.assertEqual(output[0]['name'], 'MyBaremetal')

    @patch.object(BaremetalSvc, '_get_eon_client')
    @patch.object(TokenHelpers, 'get_service_endpoint')
    @patch.object(TokenHelpers, 'get_token_for_project')
    def test_register_baremetal(self, mock_get_token_for_project,
                                mock_get_service_endpoint, mock_client):
        mock_get_token_for_project.return_value = "admin"
        mock_get_service_endpoint.return_value = "http://localhost:8070/v2.0"
        eonclient_obj = EonClientBaremetal()
        mock_client.return_value = eonclient_obj
        request = {
            api.TARGET: 'baremetal',
            api.AUTH_TOKEN: get_mock_token(),
            api.ACTION: 'POST',
            api.DATA: {
                api.OPERATION: 'register_baremetal',
                api.DATA: baremetal_data
            }
        }
        svc = BaremetalSvc(bll_request=BllRequest(request))
        svc.register_baremetal()
        self.assertEqual(svc.response[api.STATUS], 'complete')

    @patch.object(BaremetalSvc, '_get_eon_client')
    @patch.object(TokenHelpers, 'get_service_endpoint')
    @patch.object(TokenHelpers, 'get_token_for_project')
    def test_unregister_baremetal(self, mock_get_token_for_project,
                                  mock_get_service_endpoint, mock_client):
        mock_get_token_for_project.return_value = "admin"
        mock_get_service_endpoint.return_value = "http://localhost:8070/v2.0"
        eonclient_obj = EonClientBaremetal()
        mock_client.return_value = eonclient_obj
        id1 = "123"
        request = {
            api.TARGET: 'baremetal',
            api.AUTH_TOKEN: get_mock_token(),
            api.ACTION: 'DELETE',
            api.DATA: {
                api.OPERATION: 'unregister_baremetal',
                api.DATA: {'ids': [id1]}
            }
        }
        svc = BaremetalSvc(bll_request=BllRequest(request))
        output = svc.unregister_baremetal()
        self.assertEqual(output[id1][api.STATUS], 'complete')

    @patch.object(BaremetalSvc, '_get_eon_client')
    @patch.object(BaremetalSvc, 'update_job_status')
    @patch.object(TokenHelpers, 'get_service_endpoint')
    @patch.object(TokenHelpers, 'get_token_for_project')
    def test_provision_baremetal(self, mock_get_token_for_project,
                                 mock_get_service_endpoint,
                                 mock_update_job_status,
                                 mock_client):
        mock_get_token_for_project.return_value = "admin"
        mock_get_service_endpoint.return_value = "http://localhost:8070/v2.0"
        mock_update_job_status.return_value = None
        eonclient_obj = EonClientBaremetal()
        mock_client.return_value = eonclient_obj
        baremetal_data['auto_provision'] = True
        baremetal_data['os_type'] = 'rhel'
        baremetal_data['boot_from_san'] = True
        request = {
            api.TARGET: 'baremetal',
            api.AUTH_TOKEN: get_mock_token(),
            api.ACTION: 'POST',
            api.DATA: {
                api.OPERATION: 'provision_baremetal',
                api.DATA: baremetal_data
            }
        }
        svc = BaremetalSvc(bll_request=BllRequest(request))
        output = svc.provision_baremetal()
        self.assertEqual(output[api.STATUS], 'complete')
