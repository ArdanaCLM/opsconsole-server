#!/usr/bin/env python
#
# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
#

try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages


# Convenience function creating long strings below
def entry(plugin_name, class_name, file_name=None):
    return "%(plugin)s = bll.plugins.%(file)s:%(class)s" % \
        {"plugin": plugin_name,
         "file": file_name or (plugin_name + "_service"),
         "class": class_name}


setup(
    name='bll',
    version='1.0',
    author='Hewlett Packard Enterprise Development LP',
    packages=find_packages(exclude=['tests', 'tests.*', 'stubs', 'stubs.*']),
    license='(c) Copyright 2016 Hewlett Packard Enterprise Development LP'
            '(c) Copyright 2017 SUSE LLC',
    include_package_data=True,
    scripts=[],
    description='Business Logic Layer for the Operations Console',
    # The following are the first-order dependencies, excluding
    # the openstack dependencies that are installed from source.  The
    # entries here are used by the wheel build (pip wheel .) that is used
    # by the Ardana build.
    install_requires=[
        'pecan',
        'stevedore',
        'PyMySQL',
        'Pykka',
        'argparse',
        'WebOb',
        'requests',
        'dogpile.cache',
        'pyOpenSSL>=0.15.1'
    ],
    classifiers=[
        'Environment :: OpenStack',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'License :: Other/Proprietary License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
    ],
    test_suite='tests',
    zip_safe=False,

    entry_points={
        'bll.plugins': [
            entry("baremetal", "BaremetalSvc"),
            entry("catalog", "CatalogSvc"),
            entry("cinder", "CinderSvc"),
            entry("compute", "ComputeSvc"),
            entry("eon", "EONSvc"),
            entry("eula", "EulaSvc"),
            entry("ardana", "ArdSvc"),
            entry("ironic", "IronicSvc"),
            entry("monitor", "MonitorSvc"),
            entry("nova", "NovaSvc"),
            entry("objectstorage_summary", "ObjectStorageSummarySvc"),
            entry("preferences", "PreferencesSvc"),
            entry("user_group", "UserGroupSvc"),
            entry("vcenters", "IntegratedToolsSvc", "integratedtools_service"),
        ],
    },

)
