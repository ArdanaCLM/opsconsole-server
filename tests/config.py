# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
import os
from bll.hooks import RestHook

# Keystone config
KEYSTONE_HOST = os.getenv('KEYSTONE_HOST') or '192.168.245.9'
KEYSTONE_PROTOCOL = os.getenv('KEYSTONE_PROTOCOL') or 'https'
if os.getenv('KEYSTONE_PORT'):
    KEYSTONE_PORT = int(os.getenv('KEYSTONE_PORT'))
else:
    KEYSTONE_PORT = 5000

# Mysql config
DB_HOST = os.getenv('DB_HOST') or 'localhost'
DB_NAME = os.getenv('DB_NAME') or 'opsdb'
DB_USER = os.getenv('DB_USER') or 'opsconuser'
DB_PASSWORD = os.getenv('DB_PASSWORD') or 'opsconpass'
if os.getenv('DB_PORT'):
    DB_PORT = int(os.getenv('DB_PORT'))
else:
    DB_PORT = 3306

LOG_LEVEL = os.getenv('LOG_LEVEL') or 'INFO'

insecure = bool(os.getenv('INSECURE')) or False

# port for BLL to listen on when using run_tests.sh --runserver
PORT = os.getenv('PORT') or '8084'

env = os.getenv('env') or 'stdcfg'

server = {
    'port': PORT,
    'host': '0.0.0.0',
}

keystone = {
    'private_url': '%s://%s:%d' % (KEYSTONE_PROTOCOL,
                                   KEYSTONE_HOST,
                                   KEYSTONE_PORT),
    # 'insecure': True,  # Permit insecure https for dev/test
    'version': 'v2.0',
    'service_tenant': 'services',
}

db = {
    'host': DB_HOST,
    'port': DB_PORT,
    'database': DB_NAME,
    'user': DB_USER,
    'password': DB_PASSWORD,
}

app = {
    'root': 'bll.api.controllers.root.RootController',
    'modules': ['bll'],
    'hooks': [RestHook()],
    'debug': True
}

# Log everything to the console
logging = {
    'version': 1,
    'root': {'level': LOG_LEVEL, 'handlers': ['console']},
    'loggers': {
        'bll': {'level': LOG_LEVEL, 'handlers': ['consolewithtxn'],
                'propagate': False},
        # 'py.warnings': {'handlers': ['console']},
        # '__force_dict__': True
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'consolewithtxn': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'withtxn'
        },
    },
    'formatters': {
        'simple': {
            'format': '%(asctime)s %(levelname)-5.5s [%(name)-30.30s]'
                      '[%(threadName)-19.19s]            %(message).512s'
        },
        'withtxn': {
            'format': '%(asctime)s %(levelname)-5.5s [%(name)-30.30s]'
                      '[%(threadName)-19.19s] [%(txn_id)-8.8s] %(message).512s'
        },
    }
}

# BLL reads the keystone service catalog to determine which URL to use to reach
# a given service. For production, this is normally the 'internalURL'. For
# development, it is convenient to use the 'publicURL' so that a BLL running on
# a developer system can reach services running on a remote deployment.
# By default, 'internalURL' is used, unless the following block is set.
services = {
    'endpoint_type': 'publicURL',
    'interface': 'public'
}
