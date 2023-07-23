# -*- coding: utf-8 -*-
"""
Copyright: Wilde Consulting

VERSION INFO::
  License: Apache 2.0
    $Repo: git_kw_substitution
  $Author: Anders Wiklund
    $Date: 2023-07-23 06:10:33
     $Rev: 2
"""

# BUILTIN modules
from pathlib import Path
from subprocess import check_output


# ---------------------------------------------------------
#
def get_git_username() -> str:
    """ Return configured GIT repository username.

    @return: Repository username.
    """
    raw = check_output(['git', 'config', 'user.name'])

    return str(raw, encoding='utf8').rstrip()


# ---------------------------------------------------------
#
def get_git_branch() -> str:
    """ Return current GIT branch.

    @return: Current GIT branch.
    """
    raw = check_output(['git', 'branch', '--show-current'])

    return str(raw, encoding='utf8').rstrip()


# ---------------------------------------------------------
#
def get_git_root_path() -> Path:
    """ Return current GIT repository root path.

    Cache current GIT repository name.

    @return: Current GIT repository root path.
    """
    raw = check_output(['git', 'rev-parse', '--show-toplevel'])

    return Path(str(raw, encoding='utf8').rstrip())


# ---------------------------------------------------------
#
def get_git_commit_hash() -> str:
    """ Return Latest GIT commit hash.

    @return: Latest GIT commit hash.
    """
    raw = check_output(['git', 'rev-parse', '--verify', 'HEAD'])

    return str(raw, encoding='utf8').rstrip()
