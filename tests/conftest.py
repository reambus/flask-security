# -*- coding: utf-8 -*-
"""
    conftest
    ~~~~~~~~

    Test fixtures and what not

    :copyright: (c) 2017 by CERN.
    :license: MIT, see LICENSE for more details.
"""

import os
import sys

import pytest
from flask import Flask, render_template
from flask.json import JSONEncoder as BaseEncoder
from flask_babelex import Babel
from flask_mail import Mail
from speaklater import is_lazy_string
from utils import Response, populate_data


from flask_security import RoleMixin, Security, NDBUserDatastore, \
                           UserMixin, auth_required, auth_token_required, \
                           http_auth_required, login_required, \
                           roles_accepted, roles_required


class JSONEncoder(BaseEncoder):

    def default(self, o):
        if is_lazy_string(o):
            return str(o)

        return BaseEncoder.default(self, o)


@pytest.fixture()
def app(request):
    app = Flask(__name__)
    app.response_class = Response
    app.debug = True
    app.config['SECRET_KEY'] = 'secret'
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = False
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['SECURITY_PASSWORD_SALT'] = 'salty'

    for opt in ['changeable', 'recoverable', 'registerable',
                'trackable', 'passwordless', 'confirmable']:
        app.config['SECURITY_' + opt.upper()] = opt in request.keywords

    if 'settings' in request.keywords:
        for key, value in request.keywords['settings'].kwargs.items():
            app.config['SECURITY_' + key.upper()] = value

    mail = Mail(app)
    if 'babel' not in request.keywords or \
            request.keywords['babel'].args[0]:
        babel = Babel(app)
        app.babel = babel
    app.json_encoder = JSONEncoder
    app.mail = mail

    @app.route('/')
    def index():
        return render_template('index.html', content='Home Page')

    @app.route('/profile')
    @login_required
    def profile():
        return render_template('index.html', content='Profile Page')

    @app.route('/post_login')
    @login_required
    def post_login():
        return render_template('index.html', content='Post Login')

    @app.route('/http')
    @http_auth_required
    def http():
        return 'HTTP Authentication'

    @app.route('/http_custom_realm')
    @http_auth_required('My Realm')
    def http_custom_realm():
        return render_template('index.html', content='HTTP Authentication')

    @app.route('/token', methods=['GET', 'POST'])
    @auth_token_required
    def token():
        return render_template('index.html', content='Token Authentication')

    @app.route('/multi_auth')
    @auth_required('session', 'token', 'basic')
    def multi_auth():
        return render_template(
            'index.html',
            content='Session, Token, Basic auth')

    @app.route('/post_logout')
    def post_logout():
        return render_template('index.html', content='Post Logout')

    @app.route('/post_register')
    def post_register():
        return render_template('index.html', content='Post Register')

    @app.route('/admin')
    @roles_required('admin')
    def admin():
        return render_template('index.html', content='Admin Page')

    @app.route('/admin_and_editor')
    @roles_required('admin', 'editor')
    def admin_and_editor():
        return render_template('index.html', content='Admin and Editor Page')

    @app.route('/admin_or_editor')
    @roles_accepted('admin', 'editor')
    def admin_or_editor():
        return render_template('index.html', content='Admin or Editor Page')

    @app.route('/unauthorized')
    def unauthorized():
        return render_template('unauthorized.html')

    @app.route('/page1')
    def page_1():
        return 'Page 1'
    return app


@pytest.fixture()
def ndb_datastore(app):
    # init google cloud sdk
    if os.environ.get('TRAVIS'):
        build_dir = os.environ.get('TRAVIS_BUILD_DIR')
        GOOGLE_CLOUD_SDK = os.path.join(build_dir, 'google-cloud-sdk')
    else:
        GOOGLE_CLOUD_SDK = os.environ.get('GOOGLE_CLOUD_SDK', None)
        if not GOOGLE_CLOUD_SDK:
            print("""
                    No GOOGLE_CLOUD_SDK environment variable, please install
                    google cloud sdk and set environment variable
                  """)
    sdk_path = os.path.join(GOOGLE_CLOUD_SDK, 'platform/google_appengine')
    sys.path.insert(0, sdk_path)
    import dev_appserver
    dev_appserver.fix_sys_path()

    from google.appengine.ext import ndb
    from google.appengine.ext import testbed

    test_bed = testbed.Testbed()
    test_bed.activate()
    test_bed.init_datastore_v3_stub()
    test_bed.init_memcache_stub()

    class Role(ndb.Model, RoleMixin):
        name = ndb.StringProperty()
        description = ndb.StringProperty()

        def __init__(self, *args, **kwargs):
            if kwargs.get('name', None):
                kwargs['id'] = kwargs['name']
                kwargs['key'] = None
            super(Role, self).__init__(*args, **kwargs)

    class User(ndb.Model, UserMixin):
        email = ndb.StringProperty()
        username = ndb.StringProperty()
        password = ndb.StringProperty()
        active = ndb.BooleanProperty()
        role_names = ndb.StringProperty(repeated=True)
        last_login_at = ndb.DateTimeProperty()
        current_login_at = ndb.DateTimeProperty()
        last_login_ip = ndb.StringProperty()
        current_login_ip = ndb.StringProperty()
        login_count = ndb.IntegerProperty()
        confirmed_at = ndb.DateTimeProperty()

        def __init__(self, *args, **kwargs):
            roles = kwargs.get('roles')
            if isinstance(roles, list):
                kwargs['role_names'] = kwargs.pop('roles')
            super(User, self).__init__(*args, **kwargs)

        @property
        def roles(self):
            role_keys = [ndb.Key(Role, role_name) for role_name in
                         self.role_names]
            roles = ndb.get_multi(role_keys)
            return roles

        @roles.setter
        def roles(self, value):
            raise NotImplemented()

        @property
        def id(self):
            return self.key.id()

        def has_role(self, role_name):
            if role_name in self.role_names:
                return True
            else:
                return False

    class UserRole(ndb.Model):
        user_id = ndb.IntegerProperty()
        role_id = ndb.IntegerProperty()

    yield NDBUserDatastore(User, Role, UserRole)

    test_bed.deactivate()


@pytest.fixture()
def ndb_app(app, ndb_datastore):
    def create():
        app.security = Security(app, datastore=ndb_datastore)
        return app
    return create


@pytest.fixture()
def client(request, ndb_app):
    app = ndb_app()
    populate_data(app)
    return app.test_client()


@pytest.yield_fixture()
def in_app_context(request, ndb_app):
    app = ndb_app()
    with app.app_context():
        yield app


@pytest.fixture()
def get_message(app):
    def fn(key, **kwargs):
        rv = app.config['SECURITY_MSG_' + key][0] % kwargs
        return rv.encode('utf-8')
    return fn


@pytest.fixture()
def datastore(request, ndb_datastore):
    return ndb_datastore


@pytest.fixture()
def script_info(app, datastore):
    try:
        from flask.cli import ScriptInfo
    except ImportError:
        from flask_cli import ScriptInfo

    def create_app(info):
        app.config.update(**{
            'SECURITY_USER_IDENTITY_ATTRIBUTES': ('email', 'username')
        })
        app.security = Security(app, datastore=datastore)
        return app
    return ScriptInfo(create_app=create_app)
