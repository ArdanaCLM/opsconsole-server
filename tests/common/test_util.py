# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
import copy

from bll.common import util
from tests import util as test_util
from bll.common.util import scrub_passwords
from simplejson import loads
from bll.api.request import BllRequest
from pecan import conf

FTI = {
    "http_proxy_settings": {
        "no_proxy": "10.*,20.*,localhost",
        "https_proxy": "secure-proxy",
        "http_proxy": "open-proxy"
    },
    "appl_endpts": {
        "ent_appl": {
            "DCM": {
                "vip": "16.1.1.127",
                "hostname": "mgr.mycloud.com"
            },
            "CAN": {
                "public_ip": "16.1.1.129",
                "vip": "16.1.1.128",
                "hostname": "mgr.mycloud.com"
            }
        },
        "mgmt_appl": {
            "DCM": {
                "vip": "16.1.1.123",
                "hostname": "mgr.mycloud.com"
            }
        },
        "cc_appl": {
            "DCM": {
                "vip": "16.1.1.124",
                "hostname": "mgr.mycloud.com"
            },
            "CAN": {
                "public_ip": "16.1.1.126",
                "vip": "16.1.1.125",
                "hostname": "mgr.mycloud.com"
            }
        },
        "mon_appl": {
            "DCM": {
                "vip": "16.1.1.129",
                "hostname": "monitor.mycloud.com"
            }
        }
    },
    "locale_settings": {
        "locale": "lunar",
        "time_zone": "twenty-fifth-hour"
    },
    "time_server": ["time-server-1", "time-server-2"],
    "activate_ent_appl": False,
    "glance_disk_size": 512,
    "migration": False,
    "images_settings": {
        "appl_images": [{
            "avm_name": "mgmt-controller",
            "avm_type": "mgmt-controller",
            "avm_role": "CloudController",
            "avm_image": "foundation"
        }, {
            "avm_name": "enterprise1-controller",
            "avm_type": "enterprise1",
            "avm_role": "EnterpriseController",
            "avm_image": "enterprise"
        }]},
    "images_path": "\/legacy"
}

blanked_password = '****'


class Test(test_util.TestCase):

    def test_merge_empty(self):
        fti_settings = {}
        proxy = {
            "http_proxy_settings": {
                "no_proxy": "10.*,20.*,localhost",
                "https_proxy": "secure-proxy",
                "http_proxy": "open-proxy"
                },
        }

        merged = util.deepMerge(fti_settings, proxy)
        self.assertDictEqual(merged, proxy)

    def test_merge_full(self):
        fti_settings = copy.deepcopy(FTI)
        proxy = {
            "http_proxy_settings": {
                "no_proxy": "10.*,20.*,foo",
                "https_proxy": "foo-proxy",
                "http_proxy": "open-proxy"
                },
        }

        merged = util.deepMerge(fti_settings, proxy)
        result = fti_settings
        result['http_proxy_settings'] = proxy['http_proxy_settings']
        self.assertDictEqual(merged, result)

    def test_merge_timeserver(self):
        fti_settings = copy.deepcopy(FTI)
        time = {
            "time_server": [
                "time-server-4",
                "time-server-25",
                "tm-45"
            ],
        }

        merged = util.deepMerge(fti_settings, time)
        self.assertTrue(len(merged['time_server']) == 3)
        result = fti_settings
        result['time_server'] = time['time_server']
        self.assertDictEqual(merged, result)

        fti_settings = copy.deepcopy(FTI)
        time = {
            "time_server": [],
        }

        merged = util.deepMerge(fti_settings, time)
        self.assertTrue(len(merged['time_server']) == 0)
        result = fti_settings
        result['time_server'] = time['time_server']
        self.assertDictEqual(merged, result)

    def test_merge_timezone(self):
        fti_settings = copy.deepcopy(FTI)
        time = {
            "locale_settings": {
                "time_zone": "Ireland"
            },
        }

        merged = util.deepMerge(fti_settings, time)
        result = fti_settings
        result['locale_settings']['time_zone'] =\
            time["locale_settings"]["time_zone"]
        self.assertDictEqual(merged, result)

    def test_scrub_passwords_single(self):
        test_data = {
            'blah': 'something',
            'password': 'password',
            'pre_password': 'password',
            'password_post': 'password'
        }
        result = loads(scrub_passwords(test_data))
        self.assertEquals(result['password'], blanked_password)
        self.assertEquals(result['pre_password'], blanked_password)
        self.assertEquals(result['password_post'], blanked_password)
        self.assertEquals(result['blah'], 'something')

    def test_scrub_passwords_deep(self):
        test_data = {
            'blah': 'something',
            'password': 'password',
            'lvl1': {
                'a': 'a',
                'password': 'password',
                'lvl2': {
                    'b': 'b',
                    'password': 'password',
                    'lvl3': {
                        'c': 'c',
                        'password': 'password'
                    }
                }
            }
        }
        result = loads(scrub_passwords(test_data))
        self.assertEquals(result['password'], blanked_password)
        self.assertEquals(result['lvl1']['password'], blanked_password)
        self.assertEquals(result['lvl1']['lvl2']['password'], blanked_password)
        self.assertEquals(result['lvl1']['lvl2']['lvl3']['password'],
                          blanked_password)
        self.assertEquals(result['lvl1']['lvl2']['lvl3']['c'], 'c')

    '''
        This tests the case where a value is a string containing a JSON object
        and that JSON object requires password scrubbing
    '''
    def test_scrub_passwords_where_value_is_string(self):
        body = {'appliance-settings': '{"monasca-controller2": {'
                                      '"ip": "192.168.0.35", '
                                      '"keepalive-priority": "98", '
                                      '"keystone-password": "mypassword"}, '
                                      '"fakehost": {'
                                      '"ip": "192.168.0.34", '
                                      '"somedict": {'
                                      '"testpassword": "mypassword"}}}'}

        # Valid JSON doesn't allow embedded JSON as a string inside a JSON.
        # But we do this crazy stuff in our code, so let's make sure this
        # case still clears for passwords

        result = scrub_passwords(body)
        self.assertTrue('mypassword' not in result)

    def test_scrub_passwords_none(self):
        result = scrub_passwords(None)
        self.assertIsNone(result)

    def test_scrub_passwords_json_in_a_string(self):
        test_str = '{"ma1": {' \
                   '"ip": "192.168.0.35", ' \
                   '"keepalive-priority": "98", ' \
                   '"keystone-password": "mypassword"}, ' \
                   '"fakehost": {' \
                   '"ip": "192.168.0.34", ' \
                   '"somedict": {' \
                   '"testpassword": "mypassword"}}}'

        result = loads(scrub_passwords(test_str))
        self.assertEquals(result['ma1']['keystone-password'], blanked_password)
        self.assertEquals(result['fakehost']['somedict']['testpassword'],
                          blanked_password)

    '''
        To test where people put a dictionary as the only element
        in an array. <sigh>
    '''
    def test_scrub_passwords_dict_in_list_with_unicode(self):
        test_data = [{u'username': u'root',
                      u'name': u'enc1-bay2',
                      u'ip_address': u'192.168.0.71',
                      u'password': u'unset'}]
        result = loads(scrub_passwords(test_data))
        self.assertEquals(result[0]['password'], blanked_password)

    '''
        handle craziness of dumping list of items in rest_wrap.py's
        method_debug_msg()
    '''
    def test_scrub_passwords_rest_wrap_craziness(self):
        test_data = [u"action=u'GET'", u"data={u'operation': \
                     u'get_provider_networks', u'api_version': \
                     u'v1', u'ops_console_admin_password': u'unset'}",
                     u"txn_id=u'1234'", u"target=u'openstack_network'"]
        result = scrub_passwords(test_data)
        self.assertTrue('unset' not in result)

    def test_scrub_token_element(self):
        test_data = {'auth_token': 'fake-token',
                     'txn_id': '8582cdc0-c09a-4bd6-a1a8-67c5af78a1cf',
                     'target': 'deploy',
                     'data': {'operation': 'some_operation'}}
        result = loads(scrub_passwords(test_data))
        self.assertEquals(result['auth_token'], '******oken')

    def test_scrub_token_from_bll_request(self):
        test_data = {'auth_token': '4d038a60-2409-4636-b99f-280e4dc3c6fe',
                     'txn_id': '8582cdc0-c09a-4bd6-a1a8-67c5af78a1cf',
                     'target': 'deploy',
                     'data': {'operation': 'some_operation'}}
        result = scrub_passwords(BllRequest(test_data))
        self.assertNotIn('4d038a60', result)

    def test_scrub_short_token_element(self):
        test_data = {'auth_token': 'FE34',
                     'txn_id': '8582cdc0-c09a-4bd6-a1a8-67c5af78a1cf',
                     'target': 'deploy',
                     'data': {'operation': 'some_operation'}}
        result = loads(scrub_passwords(test_data))
        self.assertEquals(result['auth_token'], 'FE34')

    def test_scrub_none_token_element(self):
        test_data = {'auth_token': None,
                     'txn_id': '8582cdc0-c09a-4bd6-a1a8-67c5af78a1cf',
                     'target': 'deploy',
                     'data': {'operation': 'some_operation'}}
        result = loads(scrub_passwords(test_data))
        self.assertEquals(result['auth_token'], 'None')

    def test_scrub_json_in_a_string_craziness_1(self):
        test_data = {u'appliance-settings': u'{"monasca-controller2": \
{"ip": "192.168.0.35", "keystone-password": "unset", \
"my_token": "sometoken"}}'}
        result = scrub_passwords(test_data)
        self.assertTrue('unset' not in result)
        self.assertTrue('*****oken' in result)

    def test_scrub_json_in_a_string_craziness_2(self):
        test_data = '{"appliance-settings": "{\\"monasca-controller2\\": \
{\\"ip\\": \\"4.3.2.1\\", \
\\"keystone-password\\": \\"unset\\", \
\\"my_token\\": \\"sometoken\\"}}"}'
        result = scrub_passwords(test_data)
        self.assertTrue('unset' not in result)
        self.assertTrue('*****oken' in result)

    def test_new_txn_id(self):

        txn_id = util.new_txn_id()
        self.assertEquals(len(txn_id), 36)   # len of uuid strings

        child1 = util.new_txn_id(txn_id)
        child2 = util.new_txn_id(txn_id)
        self.assertNotEqual(child1, child2)  # better be different!

        self.assertEquals(len(txn_id) + 9, len(child1))
        self.assertEquals(len(child2), len(child1))


# Set the application environment
def set_app_env(env):
    conf['env'] = env
