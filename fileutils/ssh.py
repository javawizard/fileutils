
from fileutils.interface import Listable, Readable, Hierarchy, Writable
from fileutils.interface import ReadWrite
from fileutils.mixins import ChildrenMixin
from fileutils.constants import FILE, FOLDER, LINK
import posixpath
import stat

try:
    import paramiko
except ImportError:
    paramiko = None

if paramiko:
    class SSHFile(ReadWrite, ChildrenMixin, Listable, Readable, Hierarchy,
                  Writable):
        """
        A concrete file implementation allowing file operations to be carried
        out on a remote host via SSH and SFTP.
        
        Instances of SSHFile can be constructed around an instance of
        paramiko.SFTPClient by doing::
        
            f = SSHFile(sftp_client)
        
        They can also be obtained from :obj:`~SSHFile.connect_with_password`.
        
        SSHFile instances are reentrant context managers that close their
        underlying SFTPClient's transport on exit. This in combination with
        connect_with_password allows the following pattern to be used to
        properly clean things up after manipulating remote files::
        
            with SSHFile.connect_with_password(...) as f:
                ...do stuff with f...
                with f: # SSHFiles are reentrant, so this works fine
                    ...do more stuff with f...
                ...do even more stuff with f...
        """
        _default_block_size = 2**19 # 512 KB
        
        def __init__(self, client, client_name=None, path="/"):
            self._client = client
            self._client_name = client_name
            self._path = posixpath.normpath(path)
            self._enter_count = 0
        
        @staticmethod
        def connect_with_password(host, username, password, port=22):
            transport = paramiko.Transport((host, port))
            transport.connect(username=username, password=password)
            sftp_client = transport.open_sftp_client()
            return SSHFile(sftp_client, username + "@" + host)
        
        def _with_path(self, new_path):
            return SSHFile(self._client, self._client_name, new_path)
        
        def __enter__(self):
            self._enter_count += 1
        
        def __exit__(self, *args):
            self._enter_count -= 1
            if self._enter_count == 0:
                self.disconnect()
        
        def disconnect(self):
            self._client.get_channel().get_transport().close()
        
        def get_path_components(self, relative_to=None):
            if relative_to:
                raise NotImplementedError
            return self._path.split("/")
        
        @property
        def parent(self):
            parent = posixpath.dirname(self._path)
            if parent == self._path:
                return None
            return self._with_path(parent)
        
        def child(self, *names):
            # FIXME: Implement absolute paths
            return self._with_path(posixpath.join(self._path, *names))
        
        @property
        def link_target(self):
            if self.is_link:
                return self._client.readlink(self.path)
            else:
                return None
        
        def open_for_reading(self):
            return self._client.open(self.path, "rb")
        
        @property
        def type(self):
            try:
                s = self._client.lstat(self.path)
            except IOError:
                return None
            if stat.S_ISREG(s.st_mode):
                return FILE
            if stat.S_ISDIR(s.st_mode):
                return FOLDER
            if stat.S_ISLNK(s.st_mode):
                return LINK
            return "fileutils.OTHER"
        
        @property
        def child_names(self):
            try:
                return sorted(self._client.listdir(self._path))
            # TODO: This could mask permissions issues and such, but I'm not
            # sure there's a better way to do it without incuring extra (and
            # usually unneeded) requests against the connection
            except IOError:
                return None
        
        def create_folder(self, ignore_existing=False, recursive=False):
            if recursive:
                self.parent.create_folder(ignore_existing=True, recursive=True)
            try:
                self._client.mkdir(self._path)
            except IOError:
                if self.is_folder and ignore_existing:
                    return
                else:
                    raise
        
        def delete(self, ignore_missing=False):
            try:
                file_type = self.type
                if file_type is FOLDER: # Folder that's not a link
                    for child in self.children:
                        child.delete()
                if file_type is FOLDER:
                    self._client.rmdir(self._path)
                else:
                    self._client.remove(self._path)
            except IOError:
                if not self.exists and ignore_missing:
                    return
                else:
                    raise
        
        def link_to(self, other):
            if isinstance(other, SSHFile):
                self._client.symlink(other.path, self.path)
            elif isinstance(other, basestring):
                self._client.symlink(other, self.path)
            else:
                raise ValueError("Can't make a symlink from {!r} to {!r}".format(self, other))
        
        def open_for_writing(self, append=False):
            return self._client.open(self.path, "wb")
        
        def rename_to(self, other):
            if isinstance(other, SSHFile) and self._client is other._client:
                self._client.rename(self._path, other._path)
            else:
                return ReadWrite.rename_to(self, other)

        def __str__(self):
            if self._client_name:
                return "<fileutils.SSHFile {!r} on {!s}>".format(self._path, self._client_name)
            else:
                return "<fileutils.SSHFile {!r} on {!s}>".format(self._path, self._client)
        
        __repr__ = __str__
    
    def ssh_connect(host, username):
        import getpass
        t = paramiko.Transport((host, 22))
        t.connect(username=username, password=getpass.getpass("Password: "))
        sftp = t.open_sftp_client()
        return sftp


