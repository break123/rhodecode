# -*- coding: utf-8 -*-
"""
    rhodecode.tests.test_hg_operations
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Test suite for making push/pull operations
    
    :created_on: Dec 30, 2010
    :copyright: (c) 2010 by marcink.
    :license: LICENSE_NAME, see LICENSE_FILE for more details.
"""

import os
import shutil
import logging
from os.path import join as jn

from tempfile import _RandomNameSequence
from subprocess import Popen, PIPE

from paste.deploy import appconfig
from pylons import config
from sqlalchemy import engine_from_config

from rhodecode.lib.utils import add_cache
from rhodecode.model import init_model
from rhodecode.model import meta
from rhodecode.model.db import User, Repository
from rhodecode.lib.auth import get_crypt_password

from rhodecode.tests import TESTS_TMP_PATH, NEW_HG_REPO, HG_REPO
from rhodecode.config.environment import load_environment

conf = appconfig('config:development.ini', relative_to='./../../')
load_environment(conf.global_conf, conf.local_conf)

add_cache(conf)

USER = 'test_admin'
PASS = 'test12'
HOST = '127.0.0.1:5000'
DEBUG = True
log = logging.getLogger(__name__)


class Command(object):

    def __init__(self, cwd):
        self.cwd = cwd

    def execute(self, cmd, *args):
        """Runs command on the system with given ``args``.
        """

        command = cmd + ' ' + ' '.join(args)
        log.debug('Executing %s' % command)
        if DEBUG:
            print command
        p = Popen(command, shell=True, stdout=PIPE, stderr=PIPE, cwd=self.cwd)
        stdout, stderr = p.communicate()
        if DEBUG:
            print stdout, stderr
        return stdout, stderr

def get_session():
    engine = engine_from_config(conf, 'sqlalchemy.db1.')
    init_model(engine)
    sa = meta.Session()
    return sa


def create_test_user(force=True):
    print 'creating test user'
    sa = get_session()

    user = sa.query(User).filter(User.username == USER).scalar()

    if force and user is not None:
        print 'removing current user'
        for repo in sa.query(Repository).filter(Repository.user == user).all():
            sa.delete(repo)
        sa.delete(user)
        sa.commit()

    if user is None or force:
        print 'creating new one'
        new_usr = User()
        new_usr.username = USER
        new_usr.password = get_crypt_password(PASS)
        new_usr.email = 'mail@mail.com'
        new_usr.name = 'test'
        new_usr.lastname = 'lasttestname'
        new_usr.active = True
        new_usr.admin = True
        sa.add(new_usr)
        sa.commit()

    print 'done'


def create_test_repo(force=True):
    from rhodecode.model.repo import RepoModel
    sa = get_session()

    user = sa.query(User).filter(User.username == USER).scalar()
    if user is None:
        raise Exception('user not found')


    repo = sa.query(Repository).filter(Repository.repo_name == HG_REPO).scalar()

    if repo is None:
        print 'repo not found creating'

        form_data = {'repo_name':HG_REPO,
                     'repo_type':'hg',
                     'private':False, }
        rm = RepoModel(sa)
        rm.base_path = '/home/hg'
        rm.create(form_data, user)


def set_anonymous_access(enable=True):
    sa = get_session()
    user = sa.query(User).filter(User.username == 'default').one()
    user.active = enable
    sa.add(user)
    sa.commit()

def get_anonymous_access():
    sa = get_session()
    return sa.query(User).filter(User.username == 'default').one().active


#==============================================================================
# TESTS
#==============================================================================
def test_clone(no_errors=False):
    cwd = path = jn(TESTS_TMP_PATH, HG_REPO)

    try:
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path)
        #print 'made dirs %s' % jn(path)
    except OSError:
        raise


    clone_url = 'http://%(user)s:%(pass)s@%(host)s/%(cloned_repo)s %(dest)s' % \
                  {'user':USER,
                   'pass':PASS,
                   'host':HOST,
                   'cloned_repo':HG_REPO,
                   'dest':path}

    stdout, stderr = Command(cwd).execute('hg clone', clone_url)

    if no_errors is False:
        assert """adding file changes""" in stdout, 'no messages about cloning'
        assert """abort""" not in stderr , 'got error from clone'



def test_clone_anonymous_ok():
    cwd = path = jn(TESTS_TMP_PATH, HG_REPO)

    try:
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path)
        #print 'made dirs %s' % jn(path)
    except OSError:
        raise


    print 'checking if anonymous access is enabled'
    anonymous_access = get_anonymous_access()
    if not anonymous_access:
        print 'not enabled, enabling it '
        set_anonymous_access(enable=True)

    clone_url = 'http://%(host)s/%(cloned_repo)s %(dest)s' % \
                  {'user':USER,
                   'pass':PASS,
                   'host':HOST,
                   'cloned_repo':HG_REPO,
                   'dest':path}

    stdout, stderr = Command(cwd).execute('hg clone', clone_url)
    print stdout, stderr


    assert """adding file changes""" in stdout, 'no messages about cloning'
    assert """abort""" not in stderr , 'got error from clone'

    #disable if it was enabled
    if not anonymous_access:
        print 'disabling anonymous access'
        set_anonymous_access(enable=False)


def test_clone_wrong_credentials():
    cwd = path = jn(TESTS_TMP_PATH, HG_REPO)

    try:
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path)
        #print 'made dirs %s' % jn(path)
    except OSError:
        raise


    clone_url = 'http://%(user)s:%(pass)s@%(host)s/%(cloned_repo)s %(dest)s' % \
                  {'user':USER + 'error',
                   'pass':PASS,
                   'host':HOST,
                   'cloned_repo':HG_REPO,
                   'dest':path}

    stdout, stderr = Command(cwd).execute('hg clone', clone_url)

    assert """abort: authorization failed""" in stderr , 'no error from wrong credentials'


def test_pull():
    pass

def test_push_modify_file(f_name='setup.py'):
    cwd = path = jn(TESTS_TMP_PATH, HG_REPO)
    modified_file = jn(TESTS_TMP_PATH, HG_REPO, f_name)
    for i in xrange(5):
        cmd = """echo 'added_line%s' >> %s""" % (i, modified_file)
        Command(cwd).execute(cmd)

        cmd = """hg ci -m 'changed file %s' %s """ % (i, modified_file)
        Command(cwd).execute(cmd)

    Command(cwd).execute('hg push %s' % jn(TESTS_TMP_PATH, HG_REPO))

def test_push_new_file(commits=15):

    test_clone(no_errors=True)

    cwd = path = jn(TESTS_TMP_PATH, HG_REPO)
    added_file = jn(path, '%ssetupążźć.py' % _RandomNameSequence().next())

    Command(cwd).execute('touch %s' % added_file)

    Command(cwd).execute('hg add %s' % added_file)

    for i in xrange(commits):
        cmd = """echo 'added_line%s' >> %s""" % (i, added_file)
        Command(cwd).execute(cmd)

        cmd = """hg ci -m 'commited new %s' %s """ % (i, added_file)
        Command(cwd).execute(cmd)

    push_url = 'http://%(user)s:%(pass)s@%(host)s/%(cloned_repo)s' % \
                  {'user':USER,
                   'pass':PASS,
                   'host':HOST,
                   'cloned_repo':HG_REPO,
                   'dest':jn(TESTS_TMP_PATH, HG_REPO)}

    Command(cwd).execute('hg push --verbose --debug %s' % push_url)

def test_push_wrong_credentials():
    cwd = path = jn(TESTS_TMP_PATH, HG_REPO)
    clone_url = 'http://%(user)s:%(pass)s@%(host)s/%(cloned_repo)s' % \
                  {'user':USER + 'xxx',
                   'pass':PASS,
                   'host':HOST,
                   'cloned_repo':HG_REPO,
                   'dest':jn(TESTS_TMP_PATH, HG_REPO)}

    modified_file = jn(TESTS_TMP_PATH, HG_REPO, 'setup.py')
    for i in xrange(5):
        cmd = """echo 'added_line%s' >> %s""" % (i, modified_file)
        Command(cwd).execute(cmd)

        cmd = """hg ci -m 'commited %s' %s """ % (i, modified_file)
        Command(cwd).execute(cmd)

    Command(cwd).execute('hg push %s' % clone_url)

def test_push_wrong_path():
    cwd = path = jn(TESTS_TMP_PATH, HG_REPO)
    added_file = jn(path, 'somefile.py')

    try:
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path)
        print 'made dirs %s' % jn(path)
    except OSError:
        raise

    Command(cwd).execute("""echo '' > %s""" % added_file)
    Command(cwd).execute("""hg init %s""" % path)
    Command(cwd).execute("""hg add %s""" % added_file)

    for i in xrange(2):
        cmd = """echo 'added_line%s' >> %s""" % (i, added_file)
        Command(cwd).execute(cmd)

        cmd = """hg ci -m 'commited new %s' %s """ % (i, added_file)
        Command(cwd).execute(cmd)

    clone_url = 'http://%(user)s:%(pass)s@%(host)s/%(cloned_repo)s' % \
                  {'user':USER,
                   'pass':PASS,
                   'host':HOST,
                   'cloned_repo':HG_REPO + '_error',
                   'dest':jn(TESTS_TMP_PATH, HG_REPO)}

    stdout, stderr = Command(cwd).execute('hg push %s' % clone_url)
    assert """abort: HTTP Error 403: Forbidden"""  in stderr


if __name__ == '__main__':
    create_test_user(force=False)
    create_test_repo()
    #test_push_modify_file()
    #test_clone()
    #test_clone_anonymous_ok()

    #test_clone_wrong_credentials()

    #test_pull()
    test_push_new_file(commits=15)
    #test_push_wrong_path()
    #test_push_wrong_credentials()

