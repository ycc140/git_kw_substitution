#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright: Wilde Consulting

VERSION INFO::
  License: Apache 2.0
    $Repo: git_kw_substitution
  $Author: Anders Wiklund
    $Date: 2023-07-23 08:16:52
     $Rev: 2
"""

# BUILTIN modules
import os
import re
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from contextlib import closing

# Third party modules
import ujson as json
import pymysql as db
from filelock import FileLock

# local modules
from secrets_manager import get_secrets_file_content
from git_utilities import get_git_root_path, get_git_username, get_git_branch


# Constants
RE_KEYS = [r'\$Repo:', r'\$Author:', r'\$Date:', r'\$Rev:']
""" Regex header block dynamic keys. """
PATCHABLE_EXT_PREFIXES = {'.conf': '#---', '.env': '#---', '.ini': '#---',
                          '.py': '"""\n', '.toml': '#---', '.yaml': '#---'}
""" Header identification keys based on extension. """


# -----------------------------------------------------------------------------
#
class GitPreCommitHook:
    """
    This program performs a keyword substitution in the header block for the
    following keys B{$Rev}, B{$Author}, B{$Date} and B{$Repo} for files with
    a valid file extension.

    Since this program changes the header block in the GIT supplied files the
    initial commit will always fail. To make the second commit successful we
    need to store calculated CRC values for each file in a temporary json repo
    B{.pre-commit-repo.json} file. When the subsequent commit is executed the
    CRC values will be the same and no file change is needed.

    The repositories table is stored in a MySQL DB that needs to be placed on
    a server that all developers have access to (not localhost).

    The DB connection parameters are stored in the secrets file B{mysql_dsn}.
    The location of the secrets directory varies depending on platform. The
    following python code snippet will show you where it's at::

        >>> import site
        >>> print(f'{site.USER_BASE}/secrets')

    You need to create the secrets file in that directory with the following
    content (replace the asterix values with your own values)::

        user=*****,password=*****,host=*****,port=3306,autocommit=true

    Note that a Git commit command can call the pre-commit hook several
    times with a subset of the files being committed. This is handled
    by reserving exclusive access for the program to work.

    Handled file types are::
      - .py
      - .env
      - .ini
      - .conf
      - .toml
      - .yaml

    The program is started by the Git pre-commit hook. How to configure this
    in python is documented at: U{https://pre-commit.com/index.html}.

    A pre-commit example block in the I{.pre-commit-config.yaml} file::
        repos:
        -   repo: local
            hooks:
            -   id: header-update
                name: header-update
                entry: git_pre_commit_hook
                language: system
                stages: [commit, merge-commit]
                types: [text]

    Git provide all required values in the command line arguments::
      [0..n] => file1..n


    @type files: L{list}
    @ivar files: Files to be processed.

    @type commit_data: L{dict}
    @ivar commit_data: Holds commit data for the files being committed.

    @type infile: L{Path}
    @ivar infile: Holds commit data for the files being committed.

    @type files_modified: L{bool}
    @ivar files_modified: Tracking of when keyword substitution has happened.
    """

    # ---------------------------------------------------------
    #
    def __init__(self, args: list):
        """ The class constructor.

        Command line arguments are::
          <file1> <file2> <file3>...

        @param args: Command line arguments.
        """

        # Input parameters.
        self.files = args

        # Unique parameters.
        self.commit_data = {}
        self.infile: Path = None
        self.files_modified = False

    # ---------------------------------------------------------
    #
    def current_infile_ext(self) -> bool:
        """ Return infile file extension.

        Make sure you get the extension, even from a '.env' file.

        @return: Current infile file extension.
        """
        return self.infile.suffix or self.infile.name

    # ---------------------------------------------------------
    #
    def patchable_file(self) -> bool:
        """ Return patchable file status based on file extension.

        @return: Validation result.
        """
        ext = self.current_infile_ext()

        return ext in PATCHABLE_EXT_PREFIXES

    # ---------------------------------------------------------
    #
    def crc_of(self) -> str:
        """ Return MD5 checksum for file.

        The header block is excluded from the MD5 checksum calculation.

        @return: File MD5 checksum.

        @raise RuntimeError: when MD5 CRC calculation fails.
        """

        idx = 0
        header_active = None
        crc_sum = hashlib.md5()
        ext = self.current_infile_ext()

        try:
            with open(self.infile, 'r', encoding='utf8') as hdl:

                for idx, row in enumerate(hdl.readline(), 1):

                    if not header_active:
                        crc_sum.update(bytes(row, encoding='utf8'))
                        header_start = row.startswith(PATCHABLE_EXT_PREFIXES[ext])

                    if header_active is None and header_start:
                        header_active = True

                    elif header_active and header_start:
                        header_active = False

        except BaseException as why:
            raise RuntimeError(f'ERROR (line {idx} in file {self.infile}): {why}')

        return crc_sum.hexdigest()

    # ---------------------------------------------------------
    #
    def get_new_repository_revision(self) -> int:
        """ Return our own revision ID since GIT does not provide a useful one.

        The already existing table is initially created like this::

            CREATE TABLE git.repositories
                    (name     VARCHAR(50) PRIMARY KEY,
                     branch   VARCHAR(40) PRIMARY KEY,
                     updated  TIMESTAMP,
                     revision INT UNSIGNED DEFAULT 1,
                     hash     VARCHAR(40))

        The revision is incremented by 1 for each call to this function.

        @return: Repository revision.
        """

        updated = self.commit_data['date']
        branch = self.commit_data['branch']
        repository = self.commit_data['repo']
        config = get_secrets_file_content('mysql_dsn')
        dsn: dict = dict([tuple(x.split('=')) for x in config.split(',')])

        if 'port' in dsn:
            dsn['port'] = int(dsn['port'])

        with closing(db.connect(**dsn)) as hdl:
            cur = hdl.cursor()

            cur.execute(f"INSERT INTO git.repositories (name, updated, branch) "
                        f"VALUES('{repository}', '{updated}', '{branch}') "
                        f"ON DUPLICATE KEY UPDATE "
                        f"updated='{updated}', revision=revision+1")
            cur.execute(f"SELECT revision FROM git.repositories "
                        f"WHERE name='{repository}' AND branch='{branch}'")
            result = cur.fetchone()[0]

        return result

    # ---------------------------------------------------------
    #
    def update_header_block(self, current_crc: str):
        """ Update keyword values in the file header block.

        The following keywords are automatically updated in the header block::
          - $Rev:
          - $Repo:
          - $Date:
          - $Author:

          Rev and Author are retrieved from git. Date is a current ISO timestamp
          and Rev comes from the database.

        @param current_crc: MD5 checksum for current file.
        """

        # Only update once regardless of number of pre-commit hook thread calls.
        if self.commit_data['rev'] == 0:
            self.commit_data['rev'] = self.get_new_repository_revision()

        # Create a backup of the original file in case something fails.
        orig_file = self.infile.with_suffix('.bak')
        self.infile.rename(orig_file)

        header_active = None
        key = str(self.infile)
        self.files_modified = True
        ext = self.current_infile_ext()
        user = self.commit_data['user']
        revision = self.commit_data['rev']
        timestamp = self.commit_data['date']
        repository = self.commit_data['repo']
        self.commit_data['files'][key] = current_crc
        print(f'Updating header block in file {self.infile}')

        # To keep the original file EOL endings we need to write the rows in binary format
        # since PYTHON will automatically convert them to CRLF endings on a win32 platform.
        with (open(orig_file, 'r', encoding='utf8') as in_hdl,
              open(self.infile, 'wb') as out_hdl):

            for row in in_hdl:

                # Only look for values to change inside the header block.
                if header_active:
                    row = re.sub(fr"( +?{RE_KEYS[1]})(.+)", fr"\1 {user}", row)
                    row = re.sub(fr"( +?{RE_KEYS[3]})(.+)", fr"\1 {revision}", row)
                    row = re.sub(fr"( +?{RE_KEYS[2]})(.+)", fr"\1 {timestamp}", row)
                    row = re.sub(fr"( +?{RE_KEYS[0]})(.+)", fr"\1 {repository}", row)

                if header_active is None and row.startswith(PATCHABLE_EXT_PREFIXES[ext]):
                    header_active = True

                elif header_active and row.startswith(PATCHABLE_EXT_PREFIXES[ext]):
                    header_active = False

                out_hdl.write(bytes(row, encoding='utf8'))

        # Remove original file backup since no errors occurred.
        orig_file.unlink()

    # ---------------------------------------------------------
    #
    def process_file(self):
        """ Update key values in the file header block when MD5 checksum is different.

        The header block is excluded from the MD5 checksum calculation.
        """

        # Ignore empty files (like __init__.py).
        if os.path.getsize(self.infile) == 0:
            return

        key = str(self.infile)
        current_crc = self.crc_of()
        original_crc = self.commit_data['files'].get(key)

        if current_crc != original_crc:
            self.update_header_block(current_crc)

    # ---------------------------------------------------------
    #
    def run(self):
        """
        Process received files and change header block keywords
        if MD5 checksum differs.
        """

        root_path = get_git_root_path()
        repo_file = root_path / '.pre-commit-repo.json'
        repo_lock_file = repo_file.with_suffix('.lock')


        with FileLock(repo_lock_file, timeout=1):
            try:
                # This is the first time the GIT commit command is executed.
                if not repo_file.exists():
                    local_now = datetime.now().isoformat(' ', timespec='seconds')
                    self.commit_data = {'user': get_git_username(), 'files': {},
                                        'repo': root_path.name.lower(), 'rev': 0,
                                        'branch': get_git_branch(), 'date': local_now}

                # File exists when the GIT commit command is
                # executed for the second (or n-th) time.
                else:

                    with open(repo_file, 'r', encoding='latin1') as hdl:
                        self.commit_data = json.load(hdl)

                for item in self.files:
                    self.infile = Path(item).absolute()

                    if self.patchable_file():
                        self.process_file()

                # No point in creating a file if keyword substitution is not performed.
                if self.files_modified:

                    with open(repo_file, 'w', encoding='latin1') as hdl:
                        json.dump(self.commit_data, hdl, ensure_ascii=False, indent=2)

            except BaseException as why:
                print(f'ERROR: {why}')
                raise


# ------------------------------------------------------

if __name__ == "__main__":

    GitPreCommitHook(sys.argv[1:]).run()
