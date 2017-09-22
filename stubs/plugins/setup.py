# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from setuptools import setup, find_packages

setup(
    name='bll-services-stubs',
    version='1.0',

    description='Stub services to support bll testing',

    classifiers=['Development Status :: 3 - Alpha',
                 'License :: OSI Approved :: Apache Software License',
                 'Programming Language :: Python',
                 'Programming Language :: Python :: 2',
                 'Programming Language :: Python :: 2.7',
                 'Programming Language :: Python :: 3',
                 'Programming Language :: Python :: 3.2',
                 'Programming Language :: Python :: 3.3',
                 'Intended Audience :: Developers',
                 'Environment :: Console',
                 ],

    platforms=['Any'],

    scripts=[],

    packages=find_packages(),
    include_package_data=True,

    entry_points={'bll.plugins': [
        'composite = stubs.plugins.composite_service:CompositeSvc',
        'composite-async = stubs.plugins.composite_service:'
            'CompositeAsyncSvc',
        'general = stubs.plugins.general_service:GeneralSvc',
        'expose = stubs.plugins.expose_service:ExposeSvc',
        'unavailable = stubs.plugins.general_service:UnavailableSvc',
        ],
    },

    zip_safe=False,
)
