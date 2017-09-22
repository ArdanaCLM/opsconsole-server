# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC

import logging
import stevedore

from keystoneclient.v3 import client as ksclient
from bll import api
from bll.plugins import service
from bll.common.util import get_conf, get_val

LOG = logging.getLogger(__name__)


def on_load_failures(manager, entrypoint, exception):
    """
    Some plugins import modules that may not be present in some
    environments, which is normally not an error.
    """
    if isinstance(exception, ImportError):
        LOG.warn("Error loading %s: %s", entrypoint.module_name, exception)
    else:
        LOG.exception(exception)


class CatalogSvc(service.SvcBase):
    """
    Obtain a catalog of BLL plugins and openstack services available
    in the current environment.

    The ``target`` value for this plugin is ``catalog``. See :ref:`rest-api`
    for a full description of the request and response formats.
    """
    @service.expose()
    def get_plugins(self):
        """
        Gets the list of BLL plugin names whose dependent services are
        available.  If monasca-transform information is present in
        the config file, then ``monasca-transform`` will also be returned.

        Request format::

            "target": "catalog",
            "operation": "get_plugins"

        :return: List of BLL plugin names.  For example::

               [ "ace", "catalog", "monasca-transform", "monitor" ]

        """
        available = self._get_services()

        mgr = stevedore.extension.ExtensionManager(
            'bll.plugins',
            on_load_failure_callback=on_load_failures)

        plugins = []
        for ext in mgr:
            if ext.plugin.is_available(available):
                plugins.append(ext.name)

        # monasca-transform components will not show up in keystone's list of
        # services, so search for it's existence in config's services
        if get_conf('services.monasca.components.monasca-transform'):
            plugins.append('monasca-transform')

        return sorted(plugins)

    @service.expose()
    def get_services(self):
        """
        Gets the list of services reported by keystone.
        The list will contain both service names and service types. e.g,
        both ``identity`` and ``keystone`` will be returned for keystone.

        Request format::

            "target": "catalog",
            "operation": "get_services"

        :return: List of services reported by keystone.
            For example::

               [ "glance", "identity", "image", "keystone" ]

        """
        return sorted(self._get_services())

    @service.expose()
    def get_compute_clusters(self):
        """
        Returns compute cluster data with control plane and region data.
        Refer to an example of services in Ardana's service_topology.yml

        Request format::

            "target": "catalog",
            "operation": "get_compute_clusters"

        :return: Cluster info for all compute hosts.
        """
        nc = self._get_service_topo('services.nova.components')

        # We need to filter out non-existent compute hosts (i.e. baremetal)
        if 'hypervisor-list' in self.data:
            hyp_list = self.data['hypervisor-list']
        else:
            hyp_list = self.call_service(target='nova',
                                         operation='hypervisor-list',
                                         data={'include_status': False})
        old_cplanes = nc['nova-compute']['control_planes']
        new_cplanes = {}
        for hyp in hyp_list:
            # Using the hypervisor's 'name' doesn't always work because eon
            # uses a strange name like "domain-c7.xxxxx" that doesn't match
            # what Ardana uses in its model.  The hypervisor's service_host
            # appears to match what's in the model and works with kvm hosts,
            ch_name = hyp['service_host']

            ch_region = hyp['region']

            # go thru each control plane and see if the host and region from
            # the hypervisor list exists.  If so, add this into new_cplanes
            for cp_name, cp in old_cplanes.iteritems():
                if ch_region not in cp['regions']:
                    continue
                for type in ('resources', 'clusters'):
                    if type not in cp:
                        continue
                    for cl_name, cl_hosts in cp[type].iteritems():
                        if ch_name not in cl_hosts:
                            continue
                        new_cplanes = self._insert_cluster_data(
                            new_cplanes,
                            cp_name,
                            cp['regions'],
                            type,
                            cl_name,
                            ch_name
                        )
        nc['nova-compute']['control_planes'] = new_cplanes

        return self._derive_clusters(nc['nova-compute'])

    def _insert_cluster_data(self, cplanes, cp_name, regions, cl_type, cl_name,
                             comp_hostname):
        """
        This method adds the given comp_hostname into the appropriate area of
        the cplanes (control planes) structure, which would look something
        like this:
        cplanes = {
            cp_name: {
                'regions': regions,
                cl_type: {
                    cl_name: [<possibly existing hosts>, comp_hostname]
                }
            }
        }
        """

        if cp_name not in cplanes:
            cplanes[cp_name] = {}
        cp = cplanes[cp_name]
        cp['regions'] = regions
        if cl_type not in cp:
            cp[cl_type] = {}
        clusters = cp[cl_type]
        if cl_name not in clusters:
            clusters[cl_name] = []
        cluster = clusters[cl_name]
        if comp_hostname not in cluster:
            cluster.append(comp_hostname)
        return cplanes

    @service.expose()
    def get_swift_clusters(self):
        """
        Returns swift cluster data with control plane and region data.
        example of services in Ardana's service_topology.yml

        Request format::

            "target": "catalog",
            "operation": "get_swift_clusters"

        :return: Cluster info for all swift clusters
        """
        sc = self._get_service_topo('services.swift.components')
        return self._derive_clusters(get_val(sc, 'swift-account', {}),
                                     get_val(sc, 'swift-container', {}),
                                     get_val(sc, 'swift-object', {}),
                                     get_val(sc, 'swift-proxy', {}))

    def _get_service_topo(self, path):
        """
            Gets the requested section from service_topology.yml in
            the config file and if it doesn't succeed, try to get it from
            ardana service
        """

        # First try getting it from the config file (blazingly fast)
        comp_topo = get_conf(path)
        if comp_topo:
            return comp_topo
        else:
            # Otherwise, try getting it from ardana service (pretty slow)
            services = self.call_service(
                target='ardana',
                operation='do_path_operation',
                data={'path': '/model/cp_output/service_topology.yml'}
            )
            for key in path.split('.'):
                services = services.get(key, {})
            return services

    def _derive_clusters(self, *comps):
        """
            For each component in *comps, return a dict of clusters
            Refer to an example of services in Ardana's service_topology.yml
        """

        result = {}
        # for each component
        for comp in comps:
            control_planes = comp.get('control_planes', [])
            # for each control plane
            for cp in control_planes:
                for cluster_type in ('resources', 'clusters'):
                    clusters = control_planes[cp].get(cluster_type, [])
                    # for each cluster/resource
                    for cl in clusters:
                        # cluster names =
                        # "<control plane name>:<cluster/resource name>"
                        clust_name = "%s:%s" % (cp, cl)

                        # Concatenate the hosts to the cluster's list of hosts
                        host_list = clusters[cl] + result.get(clust_name, [])

                        # keep the cluster's list of hosts unique and sorted
                        result[clust_name] = sorted(list(set(host_list)))
        return result

    def _get_services(self):
        client = ksclient.Client(session=self.token_helper.get_session(),
                                 endpoint_type=get_conf(
                                     "services.endpoint_type",
                                     default="internalURL"),
                                 interface=get_conf("services.interface",
                                                    default="internal"),
                                 user_agent=api.USER_AGENT,
                                 verify=not get_conf("insecure"))

        services = []
        for svc in client.services.list():
            services.append(svc.name)
            services.append(svc.type)

        return services

    @service.expose()
    def get_regions(self):
        """
        Obtain a list of regions available in the current environment.

        Request format::

            "target": "catalog",
            "operation": "get_regions"
        """
        regions = []
        for region in self.token_helper.get_regions():
            regions.append({'id': region.id,
                            'description': region.description or region.id})
        return regions

    @service.expose('get_enterprise_app_endpoints')
    def get_enterprise_app_endpoints(self):
        """
        Returns a list of endpoints (URLs) of enterprise applications: oo,
        csa, mpp,

        Request format::

            "target": "catalog",
            "operation": "get_enterprise_app_endpoints"
        """
        response = {}
        endpoints = [
            {'service_type': 'enterprise-oo', 'result': 'oo'},
            {'service_type': 'enterprise-csa', 'result': 'csa'},
            {'service_type': 'enterprise-mpp', 'result': 'mpp'},
            {'service_type': 'dashboard', 'result': 'horizon'},
        ]

        for endpoint in endpoints:
            # Get public URLs since user will navigate there via a browser
            url = self.token_helper.get_service_endpoint(
                endpoint['service_type'], 'publicURL')
            response[endpoint['result']] = url
        return response
