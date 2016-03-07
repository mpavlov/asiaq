#!/usr/bin/env python
"""
Copies configuration files to the destination host and applies appropriate
ownership and permissions.
"""

import argparse
import logging
import os
import shutil
import errno
import pwd
import grp
import subprocess

HOSTCLASS_FILE_PATH = "/opt/wgen/etc/hostclass"
METADATA_FILE_NAME = "acfg.metadata"


def copy_tree(source, destination, dryrun=False):
    """Copies a file tree rooted at source to destination.
    Files that contain '~' are only copied if string after ~ matches hostclass and files
    not containing '~' are only copied if a hostclass specific version does not exist.

    This reads the hostclass from a hostclass file located at HOSTCLASS_FILE_PATH. If no
    such file exists, this raises an exception. The files will also be renamed, stripping ~
    and hostclass string after it. Permissions and file ownership are applied from
    source/METADATA_FILE_NAME, if it exists.

    :param source:  the source tree root
    :param destination:  The destination tree root
    :param dryrun:  If this is true copy_tree() will log as normal but not actually copy anything.
    :raise HostclassFileNotFound: if no hostclass file was found
    """
    if os.path.exists(HOSTCLASS_FILE_PATH):
        with open(HOSTCLASS_FILE_PATH) as hostclass_file:
            hostclass = hostclass_file.readline().strip()
            _copy_files(source, destination, hostclass, dryrun)
            _apply_metadata(source, hostclass, dryrun)
    else:
        raise HostclassFileNotFound()


def _copy_files(source, destination, hostclass, dryrun=False):
    # TODO Break this into smaller functions
    # pylint: disable=R0914
    magicsuffix = "~{0}".format(hostclass)

    for path, dirnames, filenames in os.walk(source):
        destpath = os.path.join(destination, os.path.relpath(path, source))

        for dirname in dirnames:
            spath = os.path.join(path, dirname)
            dpath = os.path.join(destpath, dirname)
            logging.info("make directory %s", dpath)
            if not dryrun:
                if not os.path.isdir(dpath):
                    os.makedirs(dpath)
                shutil.copystat(spath, dpath)

        sources = set()
        destinations = set()
        files = []

        # Add the host specific files first
        for filename in [f for f in filenames if f.endswith(magicsuffix)]:
            src = os.path.join(path, filename)
            dst = os.path.join(destpath, filename[0:-len(magicsuffix)])
            sources |= set([src])
            destinations |= set([dst])
            files += [(src, dst)]

        # Add generic files if they don't overwrite host specific files
        for filename in [f for f in filenames if "~" not in f]:
            src = os.path.join(path, filename)
            dst = os.path.join(destpath, filename)
            if dst not in destinations:
                sources |= set([src])
                destinations |= set([dst])
                files += [(src, dst)]

        # Tell user what is being skipped
        for filename in filenames:
            src_file = os.path.join(path, filename)
            if src_file not in sources:
                logging.info("skipping: %s", os.path.realpath(src_file))

        # Tell user what is being copied, copy unless this is a dry run
        for (spath, dpath) in files:
            logging.info("copying %s to %s", os.path.realpath(spath), dpath)
            if not dryrun:
                shutil.copy(spath, dpath)


def _apply_metadata(source, hostclass, dryrun=False):
    # Pylint thinks this function has too many local variables
    # pylint: disable=R0914
    metadata_file_path = os.path.join(source, METADATA_FILE_NAME)
    if not os.path.exists(metadata_file_path):
        logging.warning("Metadata file not found: %s, no permissions to apply.", metadata_file_path)
        return

    magicsuffix = "~{0}".format(hostclass)

    with open(metadata_file_path, 'r') as metadata_file:
        for line in metadata_file.readlines():
            file_metadata = line.partition('#')[0].strip()  # ignore comments and blank lines
            if not file_metadata:
                continue
            try:
                filename, permissions, owner, group = file_metadata.split()
            except Exception:
                raise ValueError("Not enough values to unpack on line: {0}".format(file_metadata))

            if "~" in filename:
                if filename.endswith(magicsuffix):
                    filename = filename[0:-len(magicsuffix)]
                else:
                    logging.info("skipping permissions: %s", filename)
                    continue

            if not os.path.exists(filename):
                logging.warning("skipping permissions (file not found): %s", filename)
                continue

            logging.info("setting ownership of %s to %s:%s", filename, owner, group)
            if not dryrun:
                uid, gid = get_or_create_ids(owner, group)
                os.chown(filename, uid, gid)

            logging.info("setting permissions of %s to %s", filename, permissions)
            if not dryrun:
                os.chmod(filename, int(permissions, 8))


class HostclassFileNotFound(EnvironmentError):
    """
    An exception indicating that the hostclass file couldn't be found.
    """
    def __init__(self):
        super(HostclassFileNotFound, self).__init__(
            errno.ENOENT,
            "Couldn't find hostclass file {0}".format(HOSTCLASS_FILE_PATH))


def get_or_create_ids(username, groupname):
    """
    Get the UID and GID for a user and group, creating the user and group if necessary.
    Users are created with no login shell: if they need a shell, downstream init scripts
    should update it.
    """
    try:
        gid = grp.getgrnam(groupname).gr_gid
    except KeyError:
        logging.info("Creating group %s", groupname)
        subprocess.call(['/usr/sbin/groupadd', '-f', groupname])
        gid = grp.getgrnam(groupname).gr_gid
    try:
        uid = pwd.getpwnam(username).pw_uid
    except KeyError:
        logging.info("Creating user %s", username)
        subprocess.call(['/usr/sbin/adduser',
                         '--system',
                         '--gid', str(gid),
                         '--shell', '/sbin/nologin',
                         username])
        uid = pwd.getpwnam(username).pw_uid
    return uid, gid


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="""
    Tool for copying trees of files. Files that contain '~' are only copied if
    string after ~ matches hostclass. The files will also be renamed,
    stripping ~ and hostclass string after it. Permissions and file ownership
    are applied from /metadata.txt at the root of the tree.
    """)
    parser.add_argument("source", help="Source location overlay directory")
    parser.add_argument("destination", help="Destination of where to overlay source directory over")
    parser.add_argument('--dry', action='store_const', const=True, default=False, help='Dry run only')

    logger = logging.getLogger('')
    logger.setLevel(logging.INFO)

    args = parser.parse_args()
    copy_tree(args.source, args.destination, args.dry)
