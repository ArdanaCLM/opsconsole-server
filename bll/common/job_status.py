# (c) Copyright 2016-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
from datetime import datetime, timedelta
import json
import logging
import pecan
import pymysql.cursors
from bll import api

LOG = logging.getLogger(__name__)


def _get_status_obj():
    # This function exists merely to facilitate injecting a test double
    # during tests where mysql is not available
    return DbStatus()


def update_job_status(txn_id, status):
    return _get_status_obj().update_job_status(txn_id, status)


def get_job_status(txn_id):
    return _get_status_obj().get_job_status(txn_id)


class DbStatus(object):
    """
    Implementation using a mysql database.  This is suitable for production
    clustered environments
    """

    def _get_connection(self):

        # Retrieve a database connection based on the config
        config = pecan.conf.db.to_dict()
        config['cursorclass'] = pymysql.cursors.DictCursor
        connection = pymysql.connect(**config)
        return connection

    def update_job_status(self, txn_id, status):
        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT `status` FROM `jobs` WHERE `id`=%s"
                cursor.execute(sql, txn_id)
                row = cursor.fetchone()
                timestamp = datetime.now()
                message = ""
                try:
                    message = json.dumps(status)
                except TypeError:
                    message = json.dumps(str(status))

                if row is None:
                    sql = """
                        INSERT INTO `jobs` (`id`, `updated_at`, `status`)
                        VALUES (%s, %s, %s)
                    """
                    parms = [txn_id, timestamp, message]
                else:
                    sql = """
                        UPDATE `jobs`
                        SET `updated_at`=%s, `status`=%s
                        WHERE `id`=%s
                    """
                    parms = [timestamp, message, txn_id]

                cursor.execute(sql, parms)

            connection.commit()

            dayold = timestamp - timedelta(days=1)

            with connection.cursor() as cursor:
                sql = "DELETE FROM `jobs` where `updated_at` < %s"
                cursor.execute(sql, dayold)
            connection.commit()
        except Exception as e:
            LOG.exception(e)

        finally:
            connection.close()

    def get_job_status(self, txn_id):

        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT `status` FROM `jobs` WHERE `id`=%s"
                cursor.execute(sql, txn_id)
                row = cursor.fetchone()
                if row is None:
                    return {api.STATUS: api.STATUS_NOT_FOUND}

                return json.loads(row.get("status"))
        except Exception as e:
            LOG.exception(e)
        finally:
            connection.close()
