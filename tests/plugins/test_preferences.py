# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from bll import api
from bll.api.request import BllRequest
from bll.plugins.service import SvcBase
import logging
import random
from tests.util import functional, TestCase, randomword, randomidentifier,\
    get_mock_token, log_level


@functional('mysql')
class TestPreferencesSvc(TestCase):

    def handle(self, action, user='test', prefs=None):

        req_dict = {
            api.TARGET: 'preferences',
            api.AUTH_TOKEN: get_mock_token(),
            api.ACTION: action
        }
        req_dict[api.DATA] = {"user": user}
        if prefs:
            req_dict[api.DATA]["prefs"] = prefs

        return SvcBase.spawn_service(BllRequest(req_dict))

    def test_crud_operations(self):
        user = randomword()
        prefs = self.create_random_dict()

        # GET preferences for a non-existent user
        with log_level(logging.CRITICAL, 'bll.plugins.service'):
            reply = self.handle('GET', user)
        self.assertEqual('error', reply[api.STATUS])

        try:
            reply = self.handle('POST', user, prefs)
            self.assertEqual('complete', reply[api.STATUS])

            reply = self.handle('GET', user)
            self.assertEqual('complete', reply[api.STATUS])
            self.assertEqual(prefs, reply[api.DATA])

            prefs = self.create_random_dict()
            reply = self.handle('PUT', user, prefs)
            self.assertEqual('complete', reply[api.STATUS])

            reply = self.handle('GET', user)
            self.assertEqual('complete', reply[api.STATUS])
            self.assertEqual(prefs, reply[api.DATA])

        finally:
            reply = self.handle('DELETE', user)
            self.assertEqual('complete', reply[api.STATUS])

            with log_level(logging.CRITICAL, 'bll.plugins.service'):
                reply = self.handle('GET', user)
            self.assertEqual('error', reply[api.STATUS])

    def test_get_from_missing_user(self):

        # GET preferences for a non-existent user
        with log_level(logging.CRITICAL, 'bll.plugins.service'):
            reply = self.handle('GET', randomword())
        self.assertEqual('error', reply[api.STATUS])

    def test_put_to_missing_user(self):

        # PUT preferences for a non-existent user
        with log_level(logging.CRITICAL, 'bll.plugins.service'):
            reply = self.handle('PUT', randomword(), randomword())
        self.assertEqual('error', reply[api.STATUS])

    def test_delete_of_missing_user(self):

        # DELETE preferences for a non-existent user should be ok
        reply = self.handle('DELETE', randomword())
        self.assertEqual('complete', reply[api.STATUS])

    def create_random_dict(self):

        # build a complicated, nested dictionary
        my_dict = {}
        my_dict[randomidentifier()] = randomword()

        nested_dict = {}
        nested_dict[randomidentifier()] = randomword()
        my_dict['dict'] = nested_dict

        nested_array = []
        nested_array.append(randomword())
        nested_array.append(random.random())
        nested_array.append(random.randint(0, 1000))
        my_dict['array'] = nested_array

        return my_dict
