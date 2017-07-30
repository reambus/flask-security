# -*- coding: utf-8 -*-
"""
    flask_security.datastore
    ~~~~~~~~~~~~~~~~~~~~~~~~

    This module contains an user datastore classes.

    :copyright: (c) 2012 by Matt Wright.
    :license: MIT, see LICENSE for more details.
"""

from .utils import get_identity_attributes, string_types
import sys


class Datastore(object):
    def __init__(self, db):
        self.db = db

    def commit(self):
        pass

    def put(self, model):
        raise NotImplementedError

    def delete(self, model):
        raise NotImplementedError


class NDBDatastore(Datastore):
    def put(self, model):
        model.put()
        return model

    def delete(self, model):
        return model.key.delete()


class UserDatastore(object):
    """Abstracted user datastore.

    :param user_model: A user model class definition
    :param role_model: A role model class definition
    """

    def __init__(self, user_model, role_model):
        self.user_model = user_model
        self.role_model = role_model

    def _prepare_role_modify_args(self, user, role):
        if isinstance(user, string_types):
            user = self.find_user(email=user)
        if isinstance(role, string_types):
            role = self.find_role(role)
        return user, role

    def _prepare_create_user_args(self, **kwargs):
        kwargs.setdefault('active', True)
        roles = kwargs.get('roles', [])
        for i, role in enumerate(roles):
            rn = role.name if isinstance(role, self.role_model) else role
            # see if the role exists
            roles[i] = self.find_role(rn)
        kwargs['roles'] = roles
        return kwargs

    def get_user(self, id_or_email):
        """Returns a user matching the specified ID or email address."""
        raise NotImplementedError

    def find_user(self, *args, **kwargs):
        """Returns a user matching the provided parameters."""
        raise NotImplementedError

    def find_role(self, *args, **kwargs):
        """Returns a role matching the provided name."""
        raise NotImplementedError

    def add_role_to_user(self, user, role):
        """Adds a role to a user.

        :param user: The user to manipulate
        :param role: The role to add to the user
        """
        user, role = self._prepare_role_modify_args(user, role)
        if role not in user.roles:
            user.roles.append(role)
            self.put(user)
            return True
        return False

    def remove_role_from_user(self, user, role):
        """Removes a role from a user.

        :param user: The user to manipulate
        :param role: The role to remove from the user
        """
        rv = False
        user, role = self._prepare_role_modify_args(user, role)
        if role in user.roles:
            rv = True
            user.roles.remove(role)
            self.put(user)
        return rv

    def toggle_active(self, user):
        """Toggles a user's active status. Always returns True."""
        user.active = not user.active
        return True

    def deactivate_user(self, user):
        """Deactivates a specified user. Returns `True` if a change was made.

        :param user: The user to deactivate
        """
        if user.active:
            user.active = False
            return True
        return False

    def activate_user(self, user):
        """Activates a specified user. Returns `True` if a change was made.

        :param user: The user to activate
        """
        if not user.active:
            user.active = True
            return True
        return False

    def create_role(self, **kwargs):
        """Creates and returns a new role from the given parameters."""

        role = self.role_model(**kwargs)
        return self.put(role)

    def find_or_create_role(self, name, **kwargs):
        """Returns a role matching the given name or creates it with any
        additionally provided parameters.
        """
        kwargs["name"] = name
        return self.find_role(name) or self.create_role(**kwargs)

    def create_user(self, **kwargs):
        """Creates and returns a new user from the given parameters."""
        kwargs = self._prepare_create_user_args(**kwargs)
        user = self.user_model(**kwargs)
        return self.put(user)

    def delete_user(self, user):
        """Deletes the specified user.

        :param user: The user to delete
        """
        self.delete(user)


class NDBUserDatastore(NDBDatastore, UserDatastore):

    def __init__(self, user_model, role_model, user_role_link):
        UserDatastore.__init__(self, user_model, role_model)
        self.user_role_link = user_role_link
        
    def create_user(self, **kwargs):
        kwargs = self._prepare_create_user_args(**kwargs)
        roles = kwargs.pop('roles')
        role_names = [r.name for r in roles]
        kwargs['roles'] = role_names
        user = self.user_model(**kwargs)
        return self.put(user)

    def add_role_to_user(self, user, role):
        user, role = self._prepare_role_modify_args(user, role)
        if role.name in user.role_names:
            return False
        else:
            user.role_names.append(role.name)
            user.put()
            return True

    def remove_role_from_user(self, user, role):
        user, role = self._prepare_role_modify_args(user, role)
        if role.name in user.role_names:
            user.role_names.remove(role.name)
            user.put()
            return True
        else:
            return False

    def get_user(self, id_or_email):
        global long
        user = None
        if sys.version_info > (3,):
            long = int
        #get user by id
        if isinstance(id_or_email, long):
            model_id = long(id_or_email)
            user = self.user_model.get_by_id(model_id)
            return user

        if isinstance(id_or_email, string_types):
            email_or_username = str(id_or_email)
            email_or_username = email_or_username.lower()
            #get user by email
            user = self.user_model.query(
                self.user_model.email == email_or_username).get()
            if user:
                return user
            #get user by username
            user = self.user_model.query(
                self.user_model.username == email_or_username).get()
            if user:
                return user
        return None

    def find_user(self, email=None, id=None):
        user = None
        if id:
            return self.user_model.get_by_id(long(id))
        if email:
            email = email.lower()
            user = self.user_model.query(self.user_model.email == email).get()
            return user
        return user

    def find_role(self, role_name):
        return self.role_model.query(self.role_model.name == role_name).get()


