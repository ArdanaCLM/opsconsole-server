# (c) Copyright 2015-2016 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
import json
from bll.plugins import service
import logging
import pecan
import pymysql.cursors

LOG = logging.getLogger(__name__)


class PreferencesSvc(service.SvcBase):
    """
    Simple service to manage user preferences.  User preferences are stored as
    JSON in a mysql database.

    The ``target`` value for this plugin is ``preferences``. See
    :ref:`rest-api` for a full description of the request and response formats.
    """

    def __init__(self, *args, **kwargs):
        super(PreferencesSvc, self).__init__(*args, **kwargs)
        config = pecan.conf.db.to_dict()
        config['cursorclass'] = pymysql.cursors.DictCursor
        self.connection = pymysql.connect(**config)

    @service.expose(action='GET')
    def _get(self):
        return self._get_mysql(self.data.get("user"))

    @service.expose(action='POST')
    def _post(self):
        self._post_mysql(self.data.get("user"),
                         self.data.get("prefs"))

    @service.expose(action='PUT')
    def _put(self):
        self._put_mysql(self.data.get("user"),
                        self.data.get("prefs"))

    @service.expose(action='DELETE')
    def _delete(self):
        self._delete_mysql(self.data.get("user"))

    # Functions for writing
    def _get_mysql(self, user):
        with self.connection.cursor() as cursor:
            sql = "SELECT `prefs` from `preferences` WHERE `username`=%s"
            cursor.execute(sql, user)
            row = cursor.fetchone()
            cursor.close()
            if row is None:
                message = self._("User {} does not exist").format(user)
                LOG.warn(message)
                self.response.error(message)
                return
            prefs = row.get("prefs")
            if isinstance(prefs, dict):
                return prefs
            return json.loads(prefs)

    def _post_mysql(self, user, prefs):
        with self.connection.cursor() as cursor:
            sql = "INSERT INTO `preferences` (`username`, `prefs`) " + \
                  "VALUES (%s,%s)"
            cursor.execute(sql, [user, json.dumps(prefs)])
            cursor.close()
        self.connection.commit()

    def _put_mysql(self, user, prefs):
        with self.connection.cursor() as cursor:
            sql = "select count(*) from preferences where username=%s"
            cursor.execute(sql, user)
            user_found = (cursor.fetchone()['count(*)'] == 1)
            if user_found:
                sql = "UPDATE `preferences` SET `prefs`=%s WHERE `username`=%s"
                cursor.execute(sql, [json.dumps(prefs), user])
            cursor.close()
        self.connection.commit()
        if not user_found:
            message = self._(
                "Cannot update non-existent user {}").format(user)
            LOG.warn(message)
            self.response.error(message)

    def _delete_mysql(self, user):
        with self.connection.cursor() as cursor:
            sql = "DELETE FROM `preferences` WHERE `username`=%s"
            cursor.execute(sql, user)
            cursor.close()
        self.connection.commit()
