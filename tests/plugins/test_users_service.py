# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
import os
from bll.common.util import get_service_tenant_name
from tests.util import functional, get_token_from_env, TestCase, \
    randomidentifier

from bll import api
from bll.plugins.user_group_service import UserGroupSvc
from bll.api.request import BllRequest


@functional('keystone')
class TestUserGroupSvc(TestCase):
    def setUp(self):
        self.token = get_token_from_env()

    def tearDown(self):
        self._user_cleanup()

    def test_get_user_list(self):
        users = self._get_user_list()
        me = os.getenv("OS_USERNAME").upper()

        found = False
        for user in users:
            if user['username'].upper() == me:
                found = True
                break

        self.assertTrue(found)

    def test_add_user_list(self):
        username = self.newuser()
        bll_request = {
            api.AUTH_TOKEN: self.token,
            'target': 'user_group',
            'data': {
                'operation': 'user_add',
                'username': username,
                'password': 'password',
                'email': 'test@email.com',
                'api_version': 'v1',
                'project_name': get_service_tenant_name(),
                }
            }

        app_svc = UserGroupSvc(bll_request=BllRequest(bll_request))

        reply = app_svc.handle()
        self.assertIn('status', reply)
        self.assertEqual('complete', reply['status'])

        users = self._get_user_list()
        user_id = None
        for user in users:
            if user['username'].upper() == username.upper():
                user_id = user['user_id']
                project_id = user['project_id']
                break
        else:
            self.fail()

        user_id_list = [user_id]

        bll_request = {
            api.AUTH_TOKEN: self.token,
            'target': 'user_group',
            'data': {
                'operation': 'users_remove',
                'user_ids': user_id_list,
                'password': 'password',
                'email': 'test@email.com',
                'project_id': project_id,
                'api_version': 'v1',
                }
            }

        app_svc = UserGroupSvc(bll_request=BllRequest(bll_request))

        reply = app_svc.handle()
        self.assertIn('status', reply)
        self.assertEqual('complete', reply['status'])

        # test the user is gone
        user_id = None
        for user in self._get_user_list():
            if username == user['username']:
                user_id = user['user_id']
                break

        if user_id is not None:
            self.assertTrue(1)

    def test_del_user_list(self):
        users_before = self._get_user_list()
        user1 = self._add_user(self.newuser(), 'tester1@test.com')
        user2 = self._add_user(self.newuser(), 'tester2@test.com')

        user_id_list = [user1, user2]
        project_id = None

        for user in self._get_user_list():
            if user1 == user['user_id']:
                project_id = user['project_id']
                break

        bll_request = {
            api.AUTH_TOKEN: self.token,
            'target': 'user_group',
            'data': {
                'operation': 'users_remove',
                'user_ids': user_id_list,
                'project_id': project_id,
                'api_version': 'v1',
                }
            }

        app_svc = UserGroupSvc(bll_request=BllRequest(bll_request))
        app_svc.handle()

        users_after = self._get_user_list()
        self.assertEqual(len(users_before), len(users_after))

    def test_update_user(self):
        user_name = self.newuser()
        email = 'UpdateMeEmail@email.com'

        update_user = self._add_user(user_name, email,
                                     project=get_service_tenant_name())

        updated_user = self.newuser()
        updated_pass = 'NewPassword'

        bll_request = {
            api.AUTH_TOKEN: self.token,
            'target': 'user_group',
            'data': {
                'operation': 'user_update',
                'user_id': update_user,
                'username': updated_user,
                'email': email,
                'password': updated_pass,
                'api_version': 'v1',
                }
            }

        app_svc = UserGroupSvc(bll_request=BllRequest(bll_request))
        reply = app_svc.handle()

        self.assertIn('status', reply)
        self.assertEqual('complete', reply['status'])

        users = self._get_user_list()
        found = False
        project_id = None
        for user in users:
            if user['username'] == updated_user:
                project_id = user['project_id']
                found = True
                break

        if found is False:
            self.assertTrue(False)

        self._del_user(update_user, project_id)

    def test_backend(self):
        bll_request = {
            api.AUTH_TOKEN: self.token,
            'target': 'user_group',
            'data': {
                'operation': 'identity_backend',
                }
            }

        app_svc = UserGroupSvc(bll_request=BllRequest(bll_request))
        reply = app_svc.handle()

        self.assertIn('status', reply)
        self.assertEqual('complete', reply['status'])

    def _add_user(self, user_name, email, password='password', project=None):
        if project is None:
            project = get_service_tenant_name()

        bll_request = {
            api.AUTH_TOKEN: self.token,
            'target': 'user_group',
            'data': {
                'operation': 'user_add',
                'username': user_name,
                'password': password,
                'email': email,
                'project_name': project,
                'api_version': 'v1',
                }
            }

        app_svc = UserGroupSvc(bll_request=BllRequest(bll_request))
        reply = app_svc.handle()
        return reply['data']

    def _get_user_list(self):
        bll_request = {
            api.AUTH_TOKEN: self.token,
            'target': 'user_group',
            'data': {
                'operation': 'users_list',
                'api_version': 'v1',
                }
            }

        app_svc = UserGroupSvc(bll_request=BllRequest(bll_request))
        reply = app_svc.handle()

        return reply['data']

    def _del_user(self, user_id, project_id=None):
        scoped = False
        if project_id is not None:
            scoped = True

        users = [user_id]
        bll_request = {
            api.AUTH_TOKEN: self.token,
            'target': 'user_group',
            'data': {
                'operation': 'users_remove',
                'user_ids': users,
                'api_version': 'v1',
                }
            }

        if scoped is True:
            bll_request['data']['project_id'] = project_id

        app_svc = UserGroupSvc(bll_request=BllRequest(bll_request))
        app_svc.handle()

    def _user_cleanup(self):
        users = self._get_user_list()

        for user in users:
            if user['username'].startswith('test_'):
                user_id = user['user_id']
                project_id = user['project_id']
                self._del_user(user_id, project_id)

    def test_default_project(self):
        bll_request = {
            api.AUTH_TOKEN: self.token,
            'target': 'user_group',
            'data': {
                'operation': 'unused'
            }
        }
        app_svc = UserGroupSvc(bll_request=BllRequest(bll_request))

        svc = get_service_tenant_name()
        # Tests a a bunch of tuples with input, and expect output as items
        tests = [
            (["admin", svc], None),
            (["admin"], None),
            ([svc], None),
            (["admin", svc, "demo"], "demo"),
            (["demo"], "demo"),
            (["demo", "foo"], "demo"),
            (["admin", svc, "foo"], "foo"),
            (["admin", svc, "demo"], "demo"),
            (["foo"], "foo"),
        ]

        # Test all of the above scenarios
        for vals, expected in tests:
            self.assertEquals(expected, app_svc._select_default_project(vals),
                              ",".join(vals))

    def newuser(self):
        return "test_%s" % randomidentifier()
