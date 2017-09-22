# (c) Copyright 2015-2017 Hewlett Packard Enterprise Development LP
# (c) Copyright 2017 SUSE LLC
import copy
from bll import api
from bll.common.exception import InvalidBllRequestException
from bll.common.util import get_conf, get_service_tenant_name
from bll.plugins import service
from keystoneclient.v3 import client as ksclient

# default OpsConsole Role = Admin
ADMIN = 'admin'
# monasca-user role required to access some items in UI
MONASCA = 'monasca-user'


class UserGroupSvc(service.SvcBase):
    """
    This service provides for managing users, groups, and projects.

    The ``target`` value for this plugin is ``user_group``. See :ref:`rest-api`
    for a full description of the request and response formats.
    """
    def __init__(self, *args, **kwargs):
        """
         Set default values for service.
        """
        super(UserGroupSvc, self).__init__(*args, **kwargs)

        self.client = self._get_ks_client()

    # a helper method to make this more unit-testable
    def _get_ks_client(self):
        return ksclient.Client(session=self.token_helper.get_domain_session(),
                               endpoint_type=get_conf("services.endpoint_type",
                                                      default="internalURL"),
                               interface=get_conf("services.interface",
                                                  default="internal"),
                               user_agent=api.USER_AGENT)

    @service.expose('identity_backend')
    def _get_identity_backend(self):
        return False

    @service.expose('users_remove')
    def _del_user_list(self):
        users = self.data.get('user_ids', [])
        for user in users:
            self.client.users.delete(user)

    @service.expose('user_update')
    def _update_user_op(self):

        user_id = self.data.get('user_id')
        username = self.data.get('username')
        email = self.data.get('email')
        password = self.data.get('password')

        if not user_id:
            return

        if username or email or password:
            data = {}
            if username:
                data['name'] = username
            if email:
                data['email'] = email
            if password:
                data['password'] = password
            self.client.users.update(user_id, **data)

    @service.expose('user_add')
    def _add_users_op(self):

        user = self.data.get('username')
        password = self.data.get('password')
        email = self.data.get('email')
        project_name = self.data.get('project_name')

        projects = self.client.projects.list()

        for project in projects:
            if project.name == project_name:
                project_id = project.id
                break
        else:
            raise InvalidBllRequestException(self._(
                "Invalid project: {}").format(project_name))

        keystone_user = self.client.users.create(name=user,
                                                 password=password,
                                                 email=email,
                                                 project_id=project_id)

        self._add_role_to_user(keystone_user, ADMIN, project_id)
        # Monasca user required for dashboard stats
        self._add_role_to_user(keystone_user, MONASCA, project_id)

        return copy.copy(keystone_user.id.encode('ascii', 'ignore'))

    # because we are using the client the user and project are keystone
    # client classes.
    def _add_role_to_user(self, user, role_name, project):
        roles = self.client.roles.list()
        role_to_add = None
        for role in roles:
            if role.name == role_name:
                role_to_add = role
                break

        self.client.roles.grant(role_to_add, user=user, project=project)

    @service.expose('get_default_project')
    def _get_default_project(self):
        projects = self.ks.get_project_list()
        return self._select_default_project(projects)

    def _select_default_project(self, projects):
        # Return the appropriate default project for creating users.  For
        # historical reasons, this is generally 'demo', if present.  Otherwise
        # return any project other than admin and the default services project.
        if 'demo' in projects:
            return 'demo'

        candidates = list(projects)
        if 'admin' in candidates:
            candidates.remove('admin')

        service_project = get_service_tenant_name()
        if service_project in candidates:
            candidates.remove(service_project)

        if candidates:
            return candidates[0]
        else:
            return None

    @service.expose('users_list')
    def _get_user_list(self):

        user_list = []
        seen_users = set()
        projects = self.client.projects.list()
        for project in projects:
            for user in self.client.users.list(project_id=project.id):
                if user.id not in seen_users:
                    user_list.append({'username': user.name,
                                      'project_id': project.id,
                                      'project_name': project.name,
                                      'email': getattr(user, 'email', ''),
                                      'user_id': user.id})
                    seen_users.add(user.id)

        return user_list

    @service.expose('project_list')
    def get_project_list(self):
        """
        Returns the project list. Duh.
        """
        project_list = []
        for project in self.client.projects.list():
            project_list.append({
                'id': project.id,
                'name': project.name,
            })

        return project_list
