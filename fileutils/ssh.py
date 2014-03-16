from fileutils.interface import BaseFile, FileSystem, MountPoint
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


class SSHFileSystem(FileSystem):
    """
    An implementation of :obj:`FileSystem <fileutils.interface.FileSystem>`
    that allows access to a remote machine using SSH and SFTP.
    """
    def __init__(self, transport, client=None, client_name=None, autoclose=True):
        self._transport = transport
        if client is None:
            client = transport.open_sftp_client()
        self._client = client
        if client_name is None:
            client_name = (transport.get_username() + "@" +
                           transport.getpeername()[0])
        self._client_name = client_name
        self._autoclose = autoclose
        self._enter_count = 0
    
    @staticmethod
    def connect(host, username=None, password=None, port=22):
        """
        Connect to an SSH server and return an SSHFileSystem connected to the
        server.
        
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
            return SSHFileSystem(transport, client_name=username + "@" + host)
        except:
            transport.close()
            raise
    
    def close(self):
        if self._autoclose:
            self._transport.close()
    
    def __del__(self):
        self.close()
    
    def child(self, *path_components):
        return SSHFile(self, posixpath.join("/", path_components))
    
    @property
    def roots(self):
        return [SSHFile(self, "/")]
    
    def __repr__(self):
        return "<fileutils.SSHFileSystem on {0!s}>".format(self._client_name)


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
    
    def __init__(self, filesystem, path="/"):
        self._filesystem = filesystem
        self._path = posixpath.normpath(path)
        while self._path.startswith("//"):
            self._path = self._path[1:]
    
    @property
    def _client(self):
        return self._filesystem._client
    
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
        return SSHFile(self._filesystem, new_path)
    
    def _exec(self, command):
        if isinstance(command, list):
            command = " ".join(pipes.quote(arg) for arg in command)
        # This is copied almost verbatim from
        # paramiko.SSHClient.exec_command
        channel = self._filesystem._transport.open_session()
        channel.exec_command(command)
        stdin = channel.makefile('wb', -1)
        stdout = channel.makefile('rb', -1)
        stderr = channel.makefile_stderr('rb', -1)
        return channel, stdin, stdout, stderr
    
    def __enter__(self):
        self._filesystem._enter_count += 1
        return self
    
    def __exit__(self, *args):
        self._filesystem._enter_count -= 1
        if self._filesystem._enter_count == 0:
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
        self._filesystem.close()
    
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
        f._fileutils_filesystem = self._filesystem
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
        f._fileutils_filesystem = self._filesystem
        return f
    
    def rename_to(self, other):
        # If we're on the same file system as other, optimize this to a remote
        # side rename
        if isinstance(other, SSHFile) and self._filesystem is other._filesystem:
            self._client.rename(self._path, other._path)
        else:
            return BaseFile.rename_to(self, other)
    
    @property
    def size(self):
        return self._client.stat(self._path).st_size

    def __str__(self):
        return "<fileutils.SSHFile {0!r} on {1!s}>".format(self._path, self._filesystem._client_name)
    
    __repr__ = __str__


def ssh_connect(host, username):
    """
    Obsolete; use SSHFileSystem.connect instead. Present only for backward
    compatibility, and will likely be going away soon.
    """
    import getpass
    t = paramiko.Transport((host, 22))
    t.connect(username=username, password=getpass.getpass("Password: "))
    sftp = t.open_sftp_client()
    return sftp


