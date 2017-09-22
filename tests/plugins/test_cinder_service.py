# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from tests.util import functional, get_token_from_env, TestCase, \
    randomidentifier
from bll.api.request import BllRequest
from bll import api
from bll.plugins.cinder_service import CinderSvc


@functional('keystone,cinder')
class TestCinderSvc(TestCase):

    def setUp(self):
        self.token = get_token_from_env()

    def test_volume_crud(self):
        volume_type = "test_" + randomidentifier()

        # Add the volume type and grab its id
        svc = CinderSvc(BllRequest(target="cinder",
                                   operation="volume_type_add",
                                   auth_token=self.token,
                                   volume_type=volume_type))
        reply = svc.handle()
        self.assertEqual(api.COMPLETE, reply[api.STATUS])

        svc = CinderSvc(BllRequest(target="cinder",
                                   auth_token=self.token,
                                   operation="volume_type_list"))
        reply = svc.handle()
        volume_types = reply[api.DATA]

        for id, vol_type in volume_types.iteritems():
            if vol_type == volume_type:
                new_id = id
                break
        else:
            self.fail("Newly created volume does not appear in list")

        svc = CinderSvc(BllRequest(target="cinder",
                                   operation="map_volume_backend",
                                   auth_token=self.token,
                                   volume_type_id=new_id,
                                   backend_name=randomidentifier()))
        reply = svc.handle()
        self.assertEqual(api.COMPLETE, reply[api.STATUS])

        # Now delete it and verify it is gone
        svc = CinderSvc(BllRequest(target="cinder",
                                   operation="volume_type_delete",
                                   auth_token=self.token,
                                   volume_type_id=new_id))
        reply = svc.handle()
        self.assertEqual(api.COMPLETE, reply[api.STATUS])

        svc = CinderSvc(BllRequest(target="cinder",
                                   operation="volume_type_list",
                                   auth_token=self.token))
        reply = svc.handle()
        self.assertNotIn(new_id, reply[api.DATA])
