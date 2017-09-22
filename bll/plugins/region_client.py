# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from bll.api.auth_token import TokenHelpers


class RegionClient(object):
    """
    Creates and returns openstack clients for the region(s) specified in the
    request.  Since client creation may be expensive, possibly
    requiring a round trip to keystone, care is taken to avoid creating
    clients until necessary and to avoid creating multiple clients for
    the same URL
    """
    def __init__(self, endpoint_type, create_func, token, region):
        self.endpoint_type = endpoint_type
        self.create_func = create_func
        self.token = token
        self.region = region

        self.clients = []

    def _get_endpoints(self):
        helper = TokenHelpers(self.token)
        endpoints = helper.get_endpoints(self.endpoint_type, self.region)

        client_list = []
        for e in endpoints:
            client_list.append({
                'endpoint': e,
                'client': None
            })

        return client_list

    def get_client(self):
        """
        Returns a single client.  This is useful for services like keystone or
        monasca where all regions share a single instance.
        """
        clients = self.get_clients()
        # return just the first client from the generator
        return clients.next()

    def get_clients(self):
        """
        Generator that returns clients and the region name, one per invocation,
        depending on the region specified in the request. If no region is
        specified (region is ``None``), then all regions will be returned.
        Otherwise, the generator will return a client for the specified region.
        """
        if not self.clients:
            self.clients = self._get_endpoints()

        for c in self.clients:
            region = c['endpoint']['region']
            url = c['endpoint']['url']
            if not c['client']:
                c['client'] = self.create_func(region=region, url=url)

            yield (c['client'], region)
