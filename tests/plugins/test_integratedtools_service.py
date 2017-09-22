# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
import random

from bll.api.request import BllRequest
from bll.common.exception import InvalidBllRequestException
from bll.plugins.integratedtools_service import IntegratedToolsSvc, \
    get_vcenter_state, REGISTERED_STATE
from mock import patch, Mock
from tests.util import TestCase, randomword, get_mock_token, \
    randomidentifier, randomip

vcenter_name = randomword()
vcenter_id = randomidentifier()
vcenter_ip = randomip()


class MockEonClient(object):

    resource_mgr = {
        "username": randomword(),
        "name": vcenter_name,
        "ip_address": vcenter_ip,
        "id": vcenter_id,
        "state": "Registered",
        "activated_clusters": 0,
        "password": randomword(),
        "type": "vcenter",
        "port": str(random.randint(1, 1024))
    }

    def get_resource_mgr_list(self):
        return [self.resource_mgr]

    def get_resource_mgr(self, id):
        if id == self.resource_mgr['id']:
            return self.resource_mgr
        return None

    def add_resource_mgr(self, vcenter_data):
        return {"id": vcenter_id,
                "name:": vcenter_name}

    def update_resource_mgr(self, vcenter_id, vcenter_data):
        return {"id": vcenter_id,
                "name": vcenter_name,
                "vcenter_meta": {"name:": vcenter_name}}

    def get_resource_list(self):
        return [{"username": randomword(),
                 "name": randomword(),
                 "ip_address": randomip(),
                 "resource_mgr_id": vcenter_id,
                 "id": randomidentifier(),
                 "state": "activated",
                 "password": randomword(),
                 "type": "esxcluster",
                 "port": str(random.randint(1, 1024))}]

    def delete_resource_mgr(self, id):
        return id

    def delete_resource(self, id):
        return id


class TestIntegratedToolsSvc(TestCase):
    @patch.object(IntegratedToolsSvc, '_get_eon_client',
                  return_value=MockEonClient())
    def test_handle_status_in_progress(self, *_):
        svc = IntegratedToolsSvc(BllRequest(
            action='GET',
            operation='vcenters',
            auth_token=get_mock_token()))
        output = svc.handle()
        self.assertEqual(output['status'], 'complete')

    @patch.object(IntegratedToolsSvc, '_get_eon_client',
                  return_value=MockEonClient())
    def test_get_vcenter_list(self, *_):
        svc = IntegratedToolsSvc(BllRequest(
            action='GET',
            operation='vcenters',
            auth_token=get_mock_token()))
        output = svc.handle()
        self.assertEqual(output['data'][0]['name'], vcenter_name)

    @patch.object(IntegratedToolsSvc, '_get_eon_client',
                  return_value=MockEonClient())
    def test_get_vcenter_count(self, *_):
        svc = IntegratedToolsSvc(BllRequest(
            action='GET',
            operation='count_vcenters',
            auth_token=get_mock_token()))
        output = svc.handle()
        self.assertEqual(output['data'], 1)

    @patch.object(IntegratedToolsSvc, '_get_eon_client')
    def test_get_vcenter_update_complete(self, *_):

        svc = IntegratedToolsSvc(BllRequest(
            action='PUT',
            operation='edit_vcenter',
            auth_token=get_mock_token(),
            data={'data': {
                'id': vcenter_id,
                'name': vcenter_name,
                'username': randomidentifier(),
                'password': randomword(),
                'ip_address': randomip(),
                'type': 'cluster'}}))

        output = svc.complete()
        self.assertEqual('complete', output['status'])

    @patch.object(IntegratedToolsSvc, '_get_eon_client', return_value=None)
    def test_get_vcenter_update_no_eon_complete(self, *_):

        svc = IntegratedToolsSvc(BllRequest(
            action='PUT',
            operation='edit_vcenter',
            auth_token=get_mock_token(),
            data={'data': {
                'id': vcenter_id,
                'name': vcenter_name,
                'username': randomidentifier(),
                'password': randomword(),
                'ip_address': randomip(),
                'type': 'cluster'}}))

        svc.update_job_status = Mock()
        svc.handle()
        output = svc.complete()

        self.assertTrue(svc.update_job_status.called)
        self.assertEqual('complete', output['status'])

    def test_get_vcenter_update_exception(self):
        attrs = {'update_resource_mgr.side_effect': Exception()}
        with patch.object(IntegratedToolsSvc, '_get_eon_client',
                          return_value=Mock(**attrs)):

            svc = IntegratedToolsSvc(BllRequest(
                action='PUT',
                operation='edit_vcenter',
                auth_token=get_mock_token(),
                data={'data': {
                    'id': vcenter_id,
                    'name': vcenter_name,
                    'username': randomidentifier(),
                    'password': randomword(),
                    'ip_address': randomip(),
                    'type': 'cluster'}}))

            output = svc.complete()
            self.assertEqual('error', output['status'])
            self.assertEqual(REGISTERED_STATE, get_vcenter_state(id))

    @patch.object(IntegratedToolsSvc, '_get_eon_client')
    def test_get_vcenter_update_no_id(self, *_):

        svc = IntegratedToolsSvc(BllRequest(
            action='PUT',
            operation='edit_vcenter',
            auth_token=get_mock_token(),
            data={'data': {
                'name': vcenter_name,
                'username': randomidentifier(),
                'password': randomword(),
                'ip_address': randomip(),
                'type': 'cluster'}}))

        with self.assertRaisesRegexp(InvalidBllRequestException,
                                     'Invalid.*vCenter id'):
            svc.handle()

    @patch.object(IntegratedToolsSvc, '_get_eon_client',
                  return_value=MockEonClient())
    def test_get_vcenter_update_invalid_id(self, *_):

        svc = IntegratedToolsSvc(BllRequest(
            action='PUT',
            operation='edit_vcenter',
            auth_token=get_mock_token(),
            data={'data': {
                'id': 'some_non-existent_id',
                'name': vcenter_name,
                'username': randomidentifier(),
                'password': randomword(),
                'ip_address': randomip(),
                'type': 'cluster'}}))

        with self.assertRaisesRegexp(InvalidBllRequestException,
                                     'not registered'):
            svc.handle()

    @patch.object(IntegratedToolsSvc, '_get_eon_client')
    def test_register_vcenter(self, *_):

        svc = IntegratedToolsSvc(BllRequest(
            action='POST',
            operation='vcenters',
            auth_token=get_mock_token(),
            data={'data': {
                'name': vcenter_name,
                'username': randomidentifier(),
                'password': randomword(),
                'ip_address': randomip(),
                'port': '443',
                'type': 'vcenter'}}))

        svc.handle()
        output = svc.complete()
        self.assertEqual('complete', output['status'])

    @patch.object(IntegratedToolsSvc, '_get_eon_client',
                  return_value=MockEonClient())
    def test_unregister_vcenter(self, *_):

        svc = IntegratedToolsSvc(BllRequest(
            action='DELETE',
            operation='vcenters',
            auth_token=get_mock_token(),
            ids={vcenter_id: vcenter_name}))

        output = svc.complete()
        self.assertEqual('complete', output['status'])
        self.assertEqual('complete', output['data'][0]['status'])
        self.assertEqual(REGISTERED_STATE, get_vcenter_state(id))

    def test_unregister_vcenter_exception(self, *_):

        attrs = {'delete_resource_mgr.side_effect': Exception('myexception')}
        with patch.object(IntegratedToolsSvc, '_get_eon_client',
                          return_value=Mock(**attrs)):

            svc = IntegratedToolsSvc(BllRequest(
                action='DELETE',
                operation='vcenters',
                auth_token=get_mock_token(),
                ids={vcenter_id: vcenter_name}))
            output = svc.complete()

            # The overall request was successful, but the individual request
            #   failed
            self.assertEqual('complete', output['status'])
            self.assertEqual('error', output['data'][0]['status'])
            self.assertEqual('myexception', output['data'][0]['data'])
            self.assertEqual(REGISTERED_STATE, get_vcenter_state(id))

    @patch.object(IntegratedToolsSvc, '_get_eon_client')
    def test_unregister_vcenter_error_missing_ids(self, *_):
        svc = IntegratedToolsSvc(BllRequest(
            action='DELETE',
            operation='vcenters',
            auth_token=get_mock_token()))
        output = svc.complete()
        self.assertEqual('error', output['status'])
        self.assertEqual(REGISTERED_STATE, get_vcenter_state(id))
