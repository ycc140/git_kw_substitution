# -*- coding: utf-8 -*-
"""
Copyright: Wilde Consulting

VERSION INFO::
  License: Apache 2.0
    $Repo: git_kw_substitution
  $Author: Anders Wiklund
    $Date: 2023-07-23 08:16:52
     $Rev: 3
"""

# BUILTIN modules
import site
from pathlib import Path


# ---------------------------------------------------------
#
def get_secrets_file_content(name: str) -> str:
    """ Return content from in the specified secrets file.

        The location of the secrets directory varies depending on platform.
        The following python code snippet will show you where it's at::

            >>> import site
            >>> print(f'{site.USER_BASE}/secrets')

        @param name: Name of secrets file (no path).
        @return: Content of specified secrets file.

        @raise RuntimeError: when secrets file is not found,
    """

    # Make sure it's working, even when in a frozen environment.
    secrets_file = Path(f'{site.getuserbase()}/secrets/{name}')

    if not secrets_file.exists():
        raise RuntimeError(f'Missing secrets file: {secrets_file}')

    with secrets_file.open() as hdl:
        result = hdl.read().rstrip()

    return result
