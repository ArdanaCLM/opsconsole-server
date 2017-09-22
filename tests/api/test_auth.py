#
# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
#
from bll.api.auth_token import TokenHelpers
from bll.common.exception import BllAuthenticationFailedException
from tests.util import TestCase, functional, create_user, delete_user

import bll.api.auth_token as auth_token


@functional('keystone')
class TestAuth(TestCase):

    def setUp(self):
        self.user = None

    def tearDown(self):
        if self.user:
            delete_user(self.user)

    def login(self):
        (self.user, password) = create_user({'admin': 'admin'},
                                            {'Default': 'admin'})

        auth_ref = auth_token.login(self.user.name, password)
        self.assertIsNotNone(auth_ref)
        self.assertIsNotNone(auth_ref.auth_token)
        self.assertTrue(auth_token.validate(auth_ref.auth_token))
        return auth_ref

    def test_valid_credentials(self):
        self.login()

    def test_invalid_credentials(self):
        self.assertRaises(Exception, auth_token.login, 'invalid', 'invalid')

    def test_get_appropriate_auth_ref(self):
        auth_ref = self.login()
        new_auth_ref = auth_token.get_appropriate_auth_ref(auth_ref.auth_token)
        self.assertEqual(auth_ref.project_name, new_auth_ref.project_name)

    def test_get_auth_ref(self):
        auth_ref = self.login()
        token = auth_ref.auth_token

        ref = auth_token.get_appropriate_auth_ref(token)
        self.assertIsNotNone(ref)
        self.assertIsNotNone(ref.auth_token)
        self.assertEqual('admin', ref.project_name)

    def test_get_auth_ref_invalid_project(self):
        auth_ref = self.login()
        token = auth_ref.auth_token
        self.assertRaises(Exception, auth_token._get_auth_ref,
                          token, 'invalid')

    def test_get_auth_ref_invalid_token(self):
        self.assertRaises(Exception, auth_token._get_auth_ref,
                          'invalid', 'admin')

    def test_get_auth_url(self):
        # Just a sanity test of the function
        self.assertIsNotNone(auth_token.get_auth_url())

    def test_helper_token(self):
        auth_ref = self.login()
        helper = TokenHelpers(auth_ref.auth_token)
        self.assertEqual(auth_ref.auth_token, helper.get_user_token())

    def test_helper_service_endpoint(self):
        auth_ref = self.login()
        helper = TokenHelpers(auth_ref.auth_token)
        self.assertIsNotNone(helper.get_service_endpoint("identity"))

    def test_login_fails_without_project_or_domain(self):
        (self.user, password) = create_user()
        with self.assertRaisesRegexp(BllAuthenticationFailedException,
                                     'access to the admin project'):
            auth_token.login(self.user.name, password)

    def test_login_fails_demo_project_admin(self):
        # Admin role on demo project, but missing the admin project
        (self.user, password) = create_user({'demo': 'admin'},
                                            {'Default': 'admin'})
        with self.assertRaisesRegexp(BllAuthenticationFailedException,
                                     'access to the admin project'):
            auth_token.login(self.user.name, password)

    def test_login_fails_admin_project(self):
        # Admin role on admin project, but missing the domain admin
        (self.user, password) = create_user({'admin': 'admin'})
        with self.assertRaisesRegexp(BllAuthenticationFailedException,
                                     'not authorized on the .* domain'):
            auth_token.login(self.user.name, password)

    def test_login_fails_multiple_admin_projects(self):
        # Admin role on both projects, but missing the domain admin
        (self.user, password) = create_user({'admin': 'admin',
                                            'demo': 'admin'})
        with self.assertRaisesRegexp(BllAuthenticationFailedException,
                                     'not authorized on the .* domain'):
            auth_token.login(self.user.name, password)

    def test_login_fails_domain_admin(self):
        # Domain admin, but lacking access to admin project
        (self.user, password) = create_user(
            {'demo': 'admin'},
            {'Default': 'admin'})
        with self.assertRaisesRegexp(BllAuthenticationFailedException,
                                     'access to the admin project'):
            auth_token.login(self.user.name, password)

    def test_login_fails_domain_project_admin(self):
        # Domain admin, and demo project admin, but lacking access to admin
        # project
        (self.user, password) = create_user({'demo': 'admin'},
                                            {'Default': 'admin'})
        with self.assertRaisesRegexp(BllAuthenticationFailedException,
                                     'access to the admin project'):
            auth_token.login(self.user.name, password)

    def test_login_other_admin(self):
        # Domain admin, and demo project admin, and monasca-user role
        # on admin project.  This should succeed
        (self.user, password) = create_user({'admin': 'monasca-user',
                                             'demo': 'admin'},
                                            {'Default': 'admin'})
        auth_ref = auth_token.login(self.user.name, password)
        token = auth_ref.auth_token
        ref = auth_token.get_appropriate_auth_ref(token)
        self.assertIsNotNone(ref)
        self.assertIsNotNone(ref.auth_token)
        self.assertEqual('demo', ref.project_name)

    def test_login_fails_domain_member(self):
        # Admin role on admin project, domain member, but missing the domain
        #   admin
        (self.user, password) = create_user({'admin': 'admin'},
                                            {'Default': '_member_'})
        with self.assertRaisesRegexp(BllAuthenticationFailedException,
                                     'not an admin of the default domain'):
            auth_token.login(self.user.name, password)
