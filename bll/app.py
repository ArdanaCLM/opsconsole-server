# (c) Copyright 2015-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC


import atexit
import logging
from pecan import make_app

from bll.common.util import setup_txn_logging

LOG = logging.getLogger(__name__)


def setup_app(config):

    app_conf = dict(config.app)

    app = make_app(
        app_conf.pop('root'),
        logging=getattr(config, 'logging', {}),
        **app_conf
    )

    setup_txn_logging()
    LOG.info('*** BLL service started ****')

    return app


@atexit.register
def app_exit():  # pragma: no coverage
    """
    Upon Teardown of application, report shutdown.
    """

    # In unit test environments, _logger_ may be undefined at this point
    if LOG:
        LOG.info('*** BLL service stopped ****')
