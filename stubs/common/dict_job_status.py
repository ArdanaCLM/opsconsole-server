# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from bll import api


class DictStatus(object):
    """
    Implementation of job status using a dictionary in memory.  This is only
    suitable for unit/functional testing in a non-clustered environment.
    """
    status_dict = {}

    def update_job_status(self, txn_id, status):
        DictStatus.status_dict[txn_id] = status

    def get_job_status(self, txn_id):
        if txn_id in DictStatus.status_dict:
            return DictStatus.status_dict[txn_id]
        else:
            return {api.STATUS: api.STATUS_NOT_FOUND}
