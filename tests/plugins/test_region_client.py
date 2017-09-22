# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from bll.api.auth_token import TokenHelpers
from bll.plugins.region_client import RegionClient
import mock
from tests.util import TestCase, randomidentifier, get_mock_token, randomurl


class TestRegionClient(TestCase):

    @mock.patch.object(TokenHelpers, 'get_endpoints')
    def test_single_region(self, _mock_endpoints):
        """
        In a single-region setup, a call to get one client must return a list
        containing just the single client, and calling them in either order
        (the list first then the single, or vise-versa) must result in just a
        single call to the create function.
        """

        _mock_endpoints.return_value = [{'region': randomidentifier(),
                                         'url': randomurl()}]
        #
        # Get all clients first, then get just a single client
        #
        create_func = mock.Mock()
        client = RegionClient(randomidentifier(), create_func,
                              get_mock_token(), randomidentifier())
        client_list = list(client.get_clients())
        self.assertEqual(1, create_func.call_count)
        single_client = client.get_client()
        self.assertEqual(1, create_func.call_count)

        self.assertEqual(1, len(client_list))
        self.assertEqual(single_client, client_list[0])

        #
        # Get one client first, then get all clients
        #
        create_func = mock.Mock()
        client = RegionClient(randomidentifier(), create_func,
                              get_mock_token(), randomidentifier())

        single_client = client.get_client()
        self.assertEqual(1, create_func.call_count)
        client_list = list(client.get_clients())
        self.assertEqual(1, create_func.call_count)

        self.assertEqual(1, len(client_list))
        self.assertEqual(single_client, client_list[0])

    @mock.patch.object(TokenHelpers, 'get_endpoints')
    def test_two_regions(self, _mock_endpoints):
        """
        In a two-region setup, a call to get one client must return just one
        client, while a call to get all clients should return a list with that
        client and one other.  Also, calling them in either order (list first
        or single client first) must generate no unnecessary calls to the
        create function.
        """
        _mock_endpoints.return_value = [
            {'region': randomidentifier(), 'url': randomurl()},
            {'region': randomidentifier(), 'url': randomurl()}]

        #
        # Get all clients first, then get just a single client
        #
        create_func = mock.Mock()
        client = RegionClient(randomidentifier(), create_func,
                              get_mock_token(), randomidentifier())
        client_list = list(client.get_clients())
        self.assertEqual(2, create_func.call_count)
        single_client = client.get_client()
        self.assertEqual(2, create_func.call_count)

        self.assertEqual(2, len(client_list))
        self.assertIn(single_client, client_list)

        #
        # Get single client first, then get all clients
        #
        create_func = mock.Mock()
        client = RegionClient(randomidentifier(), create_func,
                              get_mock_token(), randomidentifier())
        single_client = client.get_client()
        self.assertEqual(1, create_func.call_count)
        client_list = list(client.get_clients())
        self.assertEqual(2, create_func.call_count)

        self.assertEqual(2, len(client_list))
        self.assertIn(single_client, client_list)
