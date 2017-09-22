# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from bll import api
from tests import util
from bll.api.request import BllRequest


class Test(util.TestCase):

    def test_chained_creation(self):
        req1 = BllRequest(target=util.randomword(),
                          operation=util.randomword())
        req2 = BllRequest(req1)

        self.assertEquals(req1, req2)

    def test_creation_from_dict(self):
        req1 = dict(target=util.randomword(),
                    operation=util.randomword())
        req2 = BllRequest(req1)
        req3 = BllRequest(req2)

        self.assertEquals(req2, req3)

    def test_overrides(self):

        # Test that explicitly supplied values override those in the
        # request parameter of the BllRequest constructor

        req1 = BllRequest(target=util.randomword(),
                          auth_token=util.randomword(),
                          operation=util.randomword(),
                          action=util.randomword(),
                          data=util.randomdict())

        target = util.randomword()
        operation = util.randomword()
        action = util.randomword()
        auth_token = util.randomword()

        req2 = BllRequest(request=req1, target=target, operation=operation,
                          action=action, auth_token=auth_token)

        self.assertEquals(req2['action'], action)
        self.assertEquals(req2['target'], target)
        self.assertEquals(req2['auth_token'], auth_token)
        self.assertEquals(req2['data']['operation'], operation)

    def test_data_remains_gone_when_none_supplied(self):

        # Verify that when neither 'operation' nor 'data' are supplied, that
        # the resulting request has no 'data' key
        req1 = BllRequest(target=util.randomword(), action=util.randomword())

        self.assertFalse(req1.get('data'))

    def test_flattening(self):
        # Verify that we get the same result whether creating from a
        #   dictionary, individual fields, or a nested data element

        txn_id = util.randomhex()
        target = util.randomword()
        op = util.randomword()
        d = util.randomdict()

        req1 = BllRequest(dict(target=target, foo="baz", txn_id=txn_id,
                               operation=op, bar=d))
        req2 = BllRequest(target=target, foo="baz", txn_id=txn_id,
                          operation=op, bar=d)
        req3 = BllRequest(target=target, txn_id=txn_id,
                          data={'operation': op, 'foo': 'baz',
                                'bar': d})

        self.assertDictEqual(req1, req2)
        self.assertDictEqual(req2, req3)

        self.assertIn("operation", req1['data'])
        self.assertIn("foo", req1['data'])
        self.assertIn("bar", req1['data'])
        self.assertNotIn("target", req1['data'])
        self.assertNotIn("txn_id", req1['data'])

    def test_doubly_nested_data(self):

        target = util.randomword()
        d = util.randomdict()
        req = BllRequest(target=target, data={'data': d})

        # Make sure that the doubly nested data got populated correctly
        self.assertDictEqual(d, req['data']['data'])

    def test_get_data(self):
        # Verify that get_data returns all non reserved fields correctly
        req = BllRequest(target=util.randomword(),
                         action="GET",
                         foo=util.randomword(),
                         txn_id=util.randomhex(),
                         auth_token=util.randomhex(),
                         operation=util.randomword(),
                         version="1")

        data = req.get_data()

        self.assertNotIn("action", data)
        self.assertNotIn("target", data)
        self.assertNotIn("txn_id", data)
        self.assertNotIn("auth_token", data)
        self.assertNotIn("region", data)
        self.assertNotIn("data", data)
        self.assertNotIn(api.VERSION, data)
        self.assertNotIn("operation", data)

        self.assertIn("foo", data)
