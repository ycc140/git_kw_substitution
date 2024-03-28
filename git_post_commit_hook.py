#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright: Wilde Consulting

VERSION INFO::
  License: Apache 2.0
    $Repo: git_kw_substitution
  $Author: Anders Wiklund
    $Date: 2024-03-28 16:40:42
     $Rev: 1
"""

# BUILTIN modules
from pathlib import Path
from contextlib import closing

# Third party modules
import ujson as json
import pymysql as db

# local modules
from secrets_manager import get_secrets_file_content
from git_utilities import get_git_root_path, get_git_commit_hash


# ---------------------------------------------------------
#
def update_repository_tables(data: dict):
    """ Update MySQL DB tables git.repositories and git.repository_history.

    The already existing tables are initially created like this::

        CREATE TABLE git.repositories
                (name     VARCHAR(50) PRIMARY KEY,
                 branch   VARCHAR(40) PRIMARY KEY,
                 updated  TIMESTAMP,
                 revision INT UNSIGNED DEFAULT 1,
                 hash     VARCHAR(40))
        CREATE TABLE git.repository_history
                (name     VARCHAR(50) PRIMARY KEY,
                 branch   VARCHAR(40) PRIMARY KEY,
                 created  TIMESTAMP PRIMARY KEY,
                 revision INT UNSIGNED DEFAULT 1,
                 hash     VARCHAR(40))

    @param data: GIT commit data.
    """

    config = get_secrets_file_content('mysql_dsn')
    dsn: dict = dict([tuple(x.split('=')) for x in config.split(',')])

    if 'port' in dsn:
        dsn['port'] = int(dsn['port'])

    with closing(db.connect(**dsn)) as hdl:
        cur = hdl.cursor()
        cur.execute("UPDATE git.repositories SET hash='{hash}' "
                    "WHERE name='{name}' AND branch='{branch}'".format(**data))
        cur.execute("INSERT IGNORE INTO git.repository_history "
                    "(name, created, revision, hash, branch) VALUES "
                    "('{name}','{created}',{rev},'{hash}','{branch}')".format(**data))


# ---------------------------------------------------------
#
def compile_commit_data(repo_file: Path) -> dict:
    """ Return compiled pre-commit data from GIT and repo file.

    @param repo_file: Name of the .pre-commit-repo.json file.
    @return: Compiled commit data.
    """

    commit_hash = get_git_commit_hash()

    with open(repo_file, 'r', encoding='latin1') as hdl:
        commit_data = json.load(hdl)

    return {'rev': commit_data['rev'],
            'hash': commit_hash, 'branch': commit_data['branch'],
            'name': repo_file.parent.name, 'created': commit_data['date']}


# ---------------------------------------------------------
#
def run():
    """
    This program updates the git.repositories and git.repository_history
    MySQL DB tables and removes the .pre-commit-repo.json file after the
    commit command finished successfully.

    The git.repositories and git.repository_history tables are stored in a
    MySQL DB that needs to be placed on a server that all developers have
    access to (not localhost).

    The DB connection parameters are stored in the secrets' file B{mysql_dsn}.
    The location of the secrets directory varies depending on the platform.
    The following python code snippet will show you where it's at::

        >>> import site
        >>> print(f'{site.USER_BASE}/secrets')

    You need to create the secrets' file in that directory with the following
    content (replace the asterix values with your own values)::

        user=*****,password=*****,host=*****,port=3306,autocommit=true

    The program is started by the Git post-commit hook.
    How to configure
    this in python is documented at: U{https://pre-commit.com/index.html}.

    A post-commit example block in the I{.pre-commit-config.yaml} file::
        repos:
        -   repo: local
            hooks:
            -   id: post-commit-local
                name: post-commit-local
                entry: git_post_commit_hook
                language: system
                always_run: true
                stages: [post-commit, post-merge]
    """

    repo_file = get_git_root_path() / '.pre-commit-repo.json'

    if repo_file.exists():
        commit_data = compile_commit_data(repo_file)
        update_repository_tables(commit_data)
        repo_file.unlink()


# ------------------------------------------------------

if __name__ == "__main__":
    run()
