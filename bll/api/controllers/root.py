#
# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
#
from pecan import expose
from v1 import V1


class RootController(object):

    v1 = V1()

    # Return a result when querying the root document.
    @expose(generic=True, template=None, content_type='text/html')
    @expose(generic=True, template=None, content_type='application/json')
    def index(self):
        return '"Operations Console API"'
