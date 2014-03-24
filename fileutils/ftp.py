
from fileutils.interface import BaseFile, FileSystem
from fileutils.mixins import ChildrenMixin
from fileutils.constants import FILE, FOLDER
import ftplib
import posixpath

class FTPFileSystem(FileSystem):
    def __init__(self, client):
        self._client = client
    
    @property
    def roots(self):
        return [FTPFile(self, '/')]


class FTPFile(ChildrenMixin, BaseFile):
    def __init__(self, filesystem, path):
        self._filesystem = filesystem
        self._path = path
    
    @property
    def _client(self):
        return self._filesystem._client
    
    @property
    def filesystem(self):
        return self._filesystem
    
    @property
    def is_folder(self):
        # We don't actually use the working directory for anything, so we can
        # use it to detect whether we're actually a folder. I'm not aware of
        # any other way to go about this...
        try:
            self._client.cwd(self._path)
            return True
        except ftplib.error_perm as e:
            if str(e).startswith('550'):
                return False
            else:
                raise
    
    @property
    def is_file(self):
        # The only reliable way I've found to do this is to ask for the file's
        # size; we'll get back a '550 Could not get file size' if this is
        # actually a directory or a nonexistent file.
        try:
            self._client.size(self._path)
            return True
        except ftplib.error_perm as e:
            if str(e).startswith('550'):
                return False
            else:
                raise
    
    @property
    def type(self):
        if self.is_folder:
            return FOLDER
        elif self.is_file:
            return FILE
        else:
            return None
    
    @property
    def child_names(self):
        # Attempting to list files and nonexistent directories just produces an
        # empty list, so we have to see if we're dealing with a directory on
        # our own.
        if not self.is_folder:
            return None
        return [posixpath.split(name)[1] for name in self._client.nlst(self._path)]
    
    def child(self, *names):
        return FTPFile(self._filesystem, posixpath.join(self._path, *names))
    
    def create_folder(self, ignore_existing=False, recursive=False):
        if recursive and not self.parent.is_folder:
            self.parent.create_folder(recursive=True)
        if self.is_folder:
            return
        self._client.mkd(self._path)
    
    def delete(self, ignore_missing=False, recursive=False):
        # Things are somewhat complicated here. FTP doesn't give us a generic
        # "delete this, whatever it is" command, so we have to use rmd or
        # delete depending on what it is that we're deleting. But we can't just
        # try rmd and fall back to delete if it fails because it'll also fail
        # if we're a directory with children. Long story short: there's no good
        # way to generically and recursively delete a file or a folder without
        # several requests, so we do the best that we can here. This requires
        # one request if we're a file and three requests (plus requests to
        # delete children) if we're a folder, and five requests if we don't
        # actually exist (the final two to confirm that we failed because we
        # don't exist and not because of permissions issues or things like
        # that).
        #
        # First, try to delete it as a file.
        try:
            self._client.delete(self._path)
            return
        except ftplib.error_perm as e:
            if not str(e).startswith('550'):
                raise
        # Didn't work, so it's either a directory or nonexistent. List its
        # contents, ignoring any errors we might encounter.
        try:
            child_names = [posixpath.split(name)[1] for name in self._client.nlst(self._path)]
        except ftplib.Error:
            pass
        else:
            for name in child_names:
                self.child(name).delete(recursive=recursive)
        # Now try to delete it as a directory.
        try:
            self._client.rmd(self._path)
            return
        except ftplib.error_perm as e:
            if not str(e).startswith('550'):
                raise
        # Couldn't delete it as a directory. Check to see if it exists; if it
        # doesn't and ignore_missing is True, we're good. Otherwise, raise an
        # exception.
        if self.exists:
            raise Exception("Couldn't delete {0!r}".format(self))
        if not ignore_missing:
            raise Exception("Tried to delete a file that doesn't exist")


