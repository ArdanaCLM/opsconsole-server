# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
import mock
from tests.util import TestCase
from bll import api
from bll.plugins.catalog_service import CatalogSvc
from bll.api.auth_token import TokenHelpers
from bll.api.request import BllRequest
from tests.util import functional, get_token_from_env
from tests.util import get_mock_token


class TestCatalogSvc(TestCase):

    def setUp(self):
        self.mock_serv_comp = {
            '__force_dict__': True,
            "monasca": {
                "components": {
                    "monasca-transform": {
                        "control_planes": {
                            "ccp": {
                                "clusters": {
                                    "cluster1": [
                                        "standard-ccp-c1-m1-mgmt",
                                        "standard-ccp-c1-m2-mgmt",
                                        "standard-ccp-c1-m3-mgmt"
                                    ]
                                },
                                "regions": [
                                    "region1"
                                ]
                            }
                        }
                    }
                }
            },
            "nova": {
                "components": {
                    "nova-compute": {
                        "control_planes": {
                            "ccp": {
                                "regions": [
                                    "region1"
                                ],
                                "resources": {
                                    "compute": [
                                        "standard-ccp-comp0001-mgmt",
                                        "standard-ccp-comp0002-mgmt",
                                        "standard-ccp-comp0003-mgmt"
                                    ]
                                }
                            }
                        }
                    }
                }
            },
            "swift": {
                "components": {
                    "swift-account": {
                        "control_planes": {
                            "ccp": {
                                "clusters": {
                                    "cluster1": [
                                        "standard-ccp-c1-m1-mgmt",
                                        "standard-ccp-c1-m2-mgmt",
                                        "standard-ccp-c1-m3-mgmt"
                                    ]
                                },
                                "regions": [
                                    "region1"
                                ]
                            }
                        }
                    },
                    "swift-container": {
                        "control_planes": {
                            "ccp": {
                                "clusters": {
                                    "cluster1": [
                                        "standard-ccp-c1-m1-mgmt",
                                        "standard-ccp-c1-m2-mgmt",
                                        "standard-ccp-c1-m3-mgmt"
                                    ]
                                },
                                "regions": [
                                    "region1"
                                ]
                            }
                        }
                    },
                    "swift-object": {
                        "control_planes": {
                            "ccp": {
                                "clusters": {
                                    "cluster1": [
                                        "standard-ccp-c1-m1-mgmt",
                                        "standard-ccp-c1-m3-mgmt"
                                    ]
                                },
                                "regions": [
                                    "region1"
                                ]
                            }
                        }
                    },
                    "swift-proxy": {
                        "control_planes": {
                            "ccp": {
                                "clusters": {
                                    "cluster1": [
                                        "standard-ccp-c1-m1-mgmt",
                                        "standard-ccp-c1-m2-mgmt",
                                        "standard-ccp-c1-m3-mgmt",
                                        "some_host"
                                    ]
                                },
                                "regions": [
                                    "region1"
                                ]
                            }
                        }
                    }
                }
            }
        }

        # pretend comp0003 is a baremetal node, thus not in hypervisor-list
        self.mock_hyp_list = [
            {
                'name': 'standard-ccp-comp0001-mgmt',
                'region': 'region1',
                'service_host': 'standard-ccp-comp0001-mgmt'
            },
            {
                'name': 'standard-ccp-comp0002-mgmt',
                'region': 'region1',
                'service_host': 'standard-ccp-comp0002-mgmt'
            },
        ]

    def mock_call_service(self, target=None, operation=None, data=None,
                          action=None, include_status=False):
        if target == 'ardana':
            return {'services': self.mock_serv_comp}
        elif target == 'nova' and operation == 'hypervisor-list':
            return self.mock_hyp_list

    @mock.patch.object(CatalogSvc, '_get_services',
                       return_value=['identity', 'monitoring'])
    def test_get_plugins(self, _):

        request = {
            'target': 'catalog',
            'data': {'operation': 'get_plugins'}
        }

        catalog_service = CatalogSvc(bll_request=BllRequest(request))
        reply = catalog_service.handle()
        self.assertEqual('complete', reply[api.STATUS])
        plugins = reply[api.DATA]
        self.assertIn('general', plugins)
        self.assertNotIn('unavailable', plugins)

    # This is does not really add any test to the genuine unit test above,
    # but it can be useful for printing what the real plugin list is
    @functional('keystone')
    def test_get_real_plugins(self):

        token = get_token_from_env()

        request = {
            'target': 'catalog',
            'data': {'operation': 'get_plugins'},
            'auth_token': token
        }

        catalog_service = CatalogSvc(bll_request=BllRequest(request))
        reply = catalog_service.handle()
        self.assertEqual('complete', reply[api.STATUS])
        plugins = reply[api.DATA]
        # print plugins
        self.assertIn('general', plugins)
        self.assertNotIn('unavailable', plugins)

    @functional('keystone')
    def test_get_services(self):

        token = get_token_from_env()

        request = {
            'target': 'catalog',
            'data': {'operation': 'get_services'},
            'auth_token': token
        }

        catalog_service = CatalogSvc(bll_request=BllRequest(request))
        reply = catalog_service.handle()
        self.assertEqual('complete', reply[api.STATUS])
        services = reply[api.DATA]
        self.assertGreater(len(services), 2)
        self.assertIn('identity', services)
        self.assertIn('keystone', services)
        self.assertIn('monitoring', services)

    @mock.patch('bll.plugins.service.SvcBase.call_service')
    @mock.patch('bll.plugins.catalog_service.get_conf')
    def test_get_compute_clusters_from_conf(self, mock_conf, mock_legacy):
        mock_conf.return_value = self.mock_serv_comp['nova']['components']
        mock_legacy.side_effect = self.mock_call_service
        self._test_get_compute_clusters()

    @mock.patch('bll.plugins.service.SvcBase.call_service')
    @mock.patch('bll.plugins.catalog_service.get_conf')
    def test_get_compute_clusters_from_ardana(self, mock_conf, mock_legacy):
        mock_conf.return_value = None
        mock_legacy.side_effect = self.mock_call_service
        self._test_get_compute_clusters()

    def _test_get_compute_clusters(self):
        request = {
            'target': 'catalog',
            'data': {'operation': 'get_compute_clusters'},
            'auth_token': get_mock_token()
        }
        svc = CatalogSvc(bll_request=BllRequest(request))
        data = svc.handle()[api.DATA]
        self.assertTrue('ccp:compute' in data)
        self.assertEqual(len(data['ccp:compute']), 2)
        self.assertTrue('standard-ccp-comp0001-mgmt' in data['ccp:compute'])
        self.assertTrue('standard-ccp-comp0003-mgmt' not in data['ccp:compute'])

    @mock.patch('bll.plugins.catalog_service.get_conf')
    def test_get_swift_clusters_from_conf(self, mock_conf):
        mock_conf.return_value = self.mock_serv_comp['swift']['components']
        self._test_get_swift_clusters()

    @mock.patch('bll.plugins.service.SvcBase.call_service')
    @mock.patch('bll.plugins.catalog_service.get_conf')
    def test_get_swift_clusters_from_ardana(self, mock_conf, mock_legacy):
        mock_conf.return_value = None
        mock_legacy.side_effect = self.mock_call_service
        self._test_get_swift_clusters()

    def _test_get_swift_clusters(self):
        request = {
            'target': 'catalog',
            'data': {'operation': 'get_swift_clusters'},
            'auth_token': get_mock_token()
        }
        svc = CatalogSvc(bll_request=BllRequest(request))
        data = svc.handle()[api.DATA]
        self.assertTrue('ccp:cluster1' in data)
        self.assertEqual(len(data['ccp:cluster1']), 4)
        self.assertTrue('standard-ccp-c1-m1-mgmt' in data['ccp:cluster1'])
        self.assertTrue('some_host' in data['ccp:cluster1'])

    @mock.patch('bll.plugins.catalog_service.get_conf')
    @mock.patch('bll.plugins.catalog_service.CatalogSvc._get_services')
    def test_monasca_transform_avail(self, mock_serv, mock_conf):
        mon_comps = self.mock_serv_comp['monasca']['components']
        mock_conf.return_value = mon_comps
        mock_serv.return_value = []
        request = {
            'target': 'catalog',
            'data': {'operation': 'get_plugins'},
            'auth_token': get_mock_token()
        }
        svc = CatalogSvc(bll_request=BllRequest(request))
        data = svc.handle()[api.DATA]
        self.assertIn('monasca-transform', data)

    @mock.patch('bll.plugins.catalog_service.get_conf')
    @mock.patch('bll.plugins.catalog_service.CatalogSvc._get_services')
    def test_monasca_transform_notavail(self, mock_serv, mock_conf):
        mon_comps = None
        mock_conf.return_value = mon_comps
        mock_serv.return_value = []
        request = {
            'target': 'catalog',
            'data': {'operation': 'get_plugins'},
            'auth_token': get_mock_token()
        }
        svc = CatalogSvc(bll_request=BllRequest(request))
        data = svc.handle()[api.DATA]
        self.assertNotIn('monasca-transform', data)

    @functional('keystone')
    def test_get_regions(self):

        token = get_token_from_env()

        request = {
            'target': 'catalog',
            'data': {'operation': 'get_regions'},
            'auth_token': token
        }

        catalog_service = CatalogSvc(bll_request=BllRequest(request))
        reply = catalog_service.handle()
        self.assertEqual('complete', reply[api.STATUS])
        regions = reply[api.DATA]
        self.assertGreater(len(regions), 0)
        self.assertEqual('region1', regions[0]['id'])

    @mock.patch.object(TokenHelpers, 'get_service_endpoint')
    def test_get_enterprise_app_endpoints(self, mock_get_service_endpoint):

        svc = CatalogSvc(BllRequest(operation='get_enterprise_app_endpoints',
                                    auth_token=get_mock_token()))
        output = svc.handle()
        self.assertGreater(len(output['data']), 0)
