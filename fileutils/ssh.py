from fileutils.interface import BaseFile
from fileutils.mixins import ChildrenMixin
from fileutils.constants import FILE, FOLDER, LINK
import os.path # for expanduser, used to find ~/.ssh/id_rsa
import posixpath
import stat
import pipes
import getpass

try:
    import paramiko
except ImportError:
    paramiko = None


class _SSHConnection(object):
    def __init__(self, transport, client, client_name=None, autoclose=True):
        self.transport = transport
        self.client = client
        self.client_name = client_name
        self._autoclose = autoclose
        self._enter_count = 0
    
    def close(self):
        self.transport.close()
    
    def __del__(self):
        if self._autoclose:
            self.close()


class SSHFile(ChildrenMixin, BaseFile):
    """
    A concrete file implementation allowing file operations to be carried
    out on a remote host via SSH and SFTP.
    
    Instances of SSHFile can be constructed around an instance of
    paramiko.Transport by doing::
    
        f = SSHFile.from_transport(transport)
    
    They can also be obtained from :obj:`~SSHFile.connect`.
    
    SSHFile instances wrap their underlying paramiko.Transport instances with
    an object that automatically closes them on garbage collection. There's
    therefore no need to do anything special with an SSHFile when you're done
    with it, although you can use it as a context manager to force it to close
    before it's garbage collected.
    """
    _default_block_size = 2**19 # 512 KB
    _sep = "/"
    
    def __init__(self, connection, path="/"):
        self._connection = connection
        self._path = posixpath.normpath(path)
    
    @property
    def _client(self):
        return self._connection.client
    
    @staticmethod
    def connect(host, username=None, password=None, port=22):
        """
        Connect to an SSH server and return an SSHFile pointing to the server's
        root directory.
        
        If password is None, authentication with ~/.ssh/id_rsa will be
        attempted. If username is None, the current user's username will be
        used.
        """
        if username is None:
            username = getpass.getuser()
        transport = paramiko.Transport((host, port))
        try:
            transport.start_client()
            if password:
                transport.auth_password(username, password)
            else:
                # This will raise an exception if the user doesn't have a
                # ~/.ssh/id_rsa, which we just pass on
                key = paramiko.RSAKey.from_private_key_file(os.path.expanduser("~/.ssh/id_rsa"))
                transport.auth_publickey(username, key)
            sftp_client = transport.open_sftp_client()
            return SSHFile(_SSHConnection(transport, sftp_client, username + "@" + host))
        except:
            transport.close()
            raise
    
    @staticmethod
    def from_transport(transport, autoclose=True):
        sftp_client = transport.open_sftp_client()
        return SSHFile(_SSHConnection(transport, sftp_client,
                       transport.get_username() + "@" +
                       transport.getpeername()[0], autoclose=autoclose))
    
    def _with_path(self, new_path):
        return SSHFile(self._connection, new_path)
    
    def _exec(self, command):
        if isinstance(command, list):
            command = " ".join(pipes.quote(arg) for arg in command)
        # This is copied almost verbatim from
        # paramiko.SSHClient.exec_command
        channel = self._connection.transport.open_session()
        channel.exec_command(command)
        stdin = channel.makefile('wb', -1)
        stdout = channel.makefile('rb', -1)
        stderr = channel.makefile_stderr('rb', -1)
        return channel, stdin, stdout, stderr
    
    def __enter__(self):
        self._connection._enter_count += 1
        return self
    
    def __exit__(self, *args):
        self._connection._enter_count -= 1
        if self._connection._enter_count == 0:
            self.disconnect()
    
    def disconnect(self):
        """
        Disconnect this SSHFile's underlying connection.
        
        You usually won't need to call this explicitly; connections are
        automatically closed when all SSHFiles referring to them are garbage
        collected. You can use this method to force the connection to
        disconnect before all such references are garbage collected, if you
        want.
        """
        self._connection.close()
    
    def get_path_components(self, relative_to=None):
        if relative_to:
            if not isinstance(relative_to, SSHFile):
                raise ValueError("relative_to must be another SSHFile "
                                 "instance")
            return posixpath.relpath(self._path, relative_to._path).split("/")
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
        f = self._client.open(self.path, "rb")
        # Keep our connection open as long as a reference to this file is held
        f._fileutils_connection = self._connection
        return f
    
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
        if recursive and not self.parent.exists:
            self.parent.create_folder(recursive=True)
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
            raise ValueError("Can't make a symlink from {0!r} to {1!r}".format(self, other))
    
    def open_for_writing(self, append=False):
        f = self._client.open(self.path, "wb")
        f._fileutils_connection = self._connection
        return f
    
    def rename_to(self, other):
        if isinstance(other, SSHFile) and self._connection is other._connection:
            self._client.rename(self._path, other._path)
        else:
            return BaseFile.rename_to(self, other)
    
    @property
    def size(self):
        return self._client.stat(self._path).st_size

    def __str__(self):
        if self._connection.client_name:
            return "<fileutils.SSHFile {0!r} on {1!s}>".format(self._path, self._connection.client_name)
        else:
            return "<fileutils.SSHFile {0!r} on {1!s}>".format(self._path, self._client)
    
    __repr__ = __str__

def ssh_connect(host, username):
    import getpass
    t = paramiko.Transport((host, 22))
    t.connect(username=username, password=getpass.getpass("Password: "))
    sftp = t.open_sftp_client()
    return sftp


