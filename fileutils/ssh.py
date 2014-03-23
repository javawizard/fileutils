from fileutils.interface import BaseFile, FileSystem, MountPoint
from fileutils.mixins import ChildrenMixin
from fileutils.constants import FILE, FOLDER, LINK
from fileutils import local, exceptions
import os.path # for expanduser, used to find ~/.ssh/id_rsa
import posixpath
import stat
import pipes
import getpass

try:
    import paramiko
    PartialAuthentication = paramiko.ssh_exception.PartialAuthentication
except ImportError:
    paramiko = None
    PartialAuthentication = None


class SSHFileSystem(FileSystem):
    """
    A concrete FileSystem implementation allowing file operations to be carried
    out on a remote host via SSH and SFTP.
    
    Instances of SSHFileSystem can be constructed by connecting to a remote
    server with SSHFileSystem.connect::
    
        fs = SSHFileSystem.connect(hostname, username, password)
    
    They can also be constructed around an instance of paramiko.Transport::
    
        fs = SSHFileSystem.from_transport(transport)
    
    Instances of SSHFile can then be obtained using self.child(path), or from
    the :obj:`root` property, an SSHFile pointing to "/".

    SSHFileSystem instances have a __del__ that automatically closes their
    underlying paramiko.Transport on garbage collection. There's therefore no
    need to do anything special with an SSHFileSystem instance when you're done
    with it, although you can force it to close before it's garbage collected
    by calling its close() function, or by using it as a context manager::
    
        with SSHFileSystem.connect(...) as fs:
            ...
    
    .. note::
    
       SSHFileSystem does not yet implement the full FileSystem interface.
       Specifically, attempting to access SSHFileSystem.mountpoints will result
       in a NotImplementedError, and SSHFile.mountpoint is always None.
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
    def connect(host, username=None, password=None, port=22,
                auth=None):
        """
        Connect to an SSH server and return an SSHFileSystem connected to the
        server.
        
        If password is None, authentication with ~/.ssh/id_rsa will be
        attempted. If username is None, the current user's username will be
        used.
        """
        authenticators = []
        if isinstance(auth, Authenticator):
            authenticators.append(auth)
        elif isinstance(auth, list):
            authenticators.extend(auth)
        authenticators.append(SSHFileSystem.get_default_authenticator())
        if password:
            authenticators.append(Password(password))
        if username is None:
            username = getpass.getuser()
        transport = paramiko.Transport((host, port))
        try:
            transport.start_client()
            FirstOf(*authenticators).authenticate(transport, username)
            return SSHFileSystem(transport, client_name=transport.get_username() + "@" + host)
        except:
            transport.close()
            raise
    
    @staticmethod
    def get_default_authenticator():
        return FirstOf(
            Agent(),
            Key(os.path.expanduser('~/.ssh/id_rsa')),
            Key(os.path.expanduser('~/.ssh/id_dsa')),
            Key(os.path.expanduser('~/ssh/id_rsa')),
            Key(os.path.expanduser('~/ssh/id_dsa')),
        )
    
    def close(self):
        if self._autoclose:
            self._transport.close()
    
    def __del__(self):
        self.close()
    
    def __enter__(self):
        self._enter_count += 1
        return self
    
    def __exit__(self, *args):
        self._enter_count -= 1
        if self._filesystem._enter_count == 0:
            self.close()
    
    def child(self, *path_components):
        return SSHFile(self, posixpath.join("/", path_components))
    
    @property
    def roots(self):
        return [SSHFile(self, "/")]
    
    def __repr__(self):
        return "<fileutils.SSHFileSystem on {0!s}>".format(self._client_name)


class Authenticator(object):
    """
    Class of methods that can be used to authenticate to an SSH server.
    
    The various subclasses
    """
    def authenticate(self, transport):
        """
        Authenticate to the specified transport using this method.
        """
        raise NotImplementedError


class FirstOf(Authenticator):
    """
    An authentication method that tries several other methods and succeeds once
    one of them does. If all of the methods fail, it fails.
    
    If one of them raises PartialAuthentication to indicate that it succeeded
    but didn't conclude authentication, FirstOf continues on with the rest of
    the authentication methods, then re-raises PartialAuthentication. I'm still
    debating exactly how partial authentication should work, so this could
    change.
    """
    def __init__(self, *methods):
        """
        Create a new FirstOf authentication method that will attempt to
        authenticate using the specified Authenticator instances.
        """
        self._methods = [e for m in methods for e in (m._methods if type(m) is FirstOf else [m])]
    
    def authenticate(self, transport, username):
        failures = []
        for method in self._methods:
            try:
                method.authenticate(transport, username)
                return
            except paramiko.AuthenticationException as e:
                failures.append(e)
        partial_types = [t for e in failures if isinstance(e, PartialAuthentication) for t in e.allowed_types]
        if partial_types:
            raise PartialAuthentication(partial_types)
        raise paramiko.AuthenticationException(
            'Authentication methods {0!r} failed with errors {1!r}'
            .format(self._methods, failures))
    
    def __repr__(self):
        return 'FirstOf({0})'.format(', '.join(repr(m) for m in self._methods))
    
    __str__ = __repr__


class Password(Authenticator):
    """
    An authentication method that authenticates using a password.
    """
    def __init__(self, password, fallback=True):
        """
        Create a Password authentication method that will authenticate using
        the specified password.
        
        username, password, and fallback are passed onto the underlying call
        to paramiko.Transport.auth_password.
        """
        self._password = password
        self._fallback = fallback
    
    def authenticate(self, transport, username):
        types = transport.auth_password(username, self._password, fallback=self._fallback)
        if types:
            raise PartialAuthentication(types)
    
    def __repr__(self):
        # Just in case...
        return 'Password(...)'
    
    __str__ = __repr__


class Key(Authenticator):
    """
    An authentication method that authenticates using a private key.
    
    Currently, only RSA keys are supported, and keys that require a passphrase
    are not yet supported. I plan on adding such support in the near future.
    """
    def __init__(self, key, required=False):
        """
        Create a Key authentication method that will authenticate using the
        specified private key.
        
        The key can be an instance of any subclass of paramiko.PKey (such as
        paramiko.RSAKey), a BaseFile instance (in which case the file in
        question will be read and its contents used as the key), or a string
        representing a local path to a key file.
        
        If required is False and key is a BaseFile or a local path that does
        not exist, the returned Key instance will do nothing (but raise an
        AuthenticationException). Otherwise, a
        fileutils.exceptions.FileNotFoundError will be raised.
        """
        # If it's already a PKey instance, just store it
        if isinstance(key, paramiko.PKey):
            self._key = key
            return
        # If it's a file path, convert it into a File instance
        if isinstance(key, basestring):
            key = local.File(key)
        # If it's a BaseFile instance, open it.
        if isinstance(key, BaseFile):
            try:
                key = key.open()
            except exceptions.FileNotFoundError:
                if required:
                    raise
                else:
                    self._key = None
                    return
        # It'll be a file-like object at this point
        for key_type in (paramiko.RSAKey, paramiko.DSSKey,
                         paramiko.ECDSAKey):
            try:
                # TODO: Add support for key passwords
                self._key = key_type.from_private_key(key)
                return
            # I've got https://github.com/paramiko/paramiko/pull/293
            # open to raise a more specific exception,
            # KeyFormatException, on invalid key data, but until that
            # goes through we have to just catch all SSHExceptions here
            except paramiko.SSHException:
                # Not a key of this format. Seek the stream back to 0 and then
                # try the next format.
                key.seek(0)
                continue
        # Key wasn't in any known format, so raise an exception.
        raise Exception("Unsupported key format")
    
    def authenticate(self, transport, username):
        if self._key is None:
            raise paramiko.AuthenticationException('The underlying key file does not exist')
        types = transport.auth_publickey(username, self._key)
        if types:
            raise PartialAuthentication(types)


class Agent(Authenticator):
    """
    An authentication method that authenticates using an SSH agent.
    """
    def __init__(self):
        """
        Create a new Agent authenticate method that will authenticate using the
        keys made available by the local SSH agent.
        """
        pass
    
    def authenticate(self, transport, username):
        agent = paramiko.Agent()
        keys = agent.get_keys()
        FirstOf(*[Key(key) for key in keys]).authenticate(transport, username)
    
    def __repr__(self):
        return 'Agent()'
    
    __str__ = __repr__


class User(FirstOf):
    def __init__(self, username, *authenticators):
        FirstOf.__init__(self, *authenticators)
        self._username = username
    
    def authenticate(self, transport, username):
        FirstOf.authenticate(self, transport, self._username)
    
    def __repr__(self):
        return 'User({0})'.format(', '.join(repr(m) for m in self._methods))
    
    __str__ = __repr__


class SSHFile(ChildrenMixin, BaseFile):
    """
    A concrete BaseFile implementation allowing file operations to be carried
    out on a remote host via SSH and SFTP.
    
    Instances of SSHFile can be obtained from an SSHFileSystem via its
    child(path) method, or from its root property::
    
        f = SSHFileSystem.connect(hostname, username, password).root
        f = SSHFileSystem(paramiko_transport).root
        f = SSHFileSystem(paramiko_transport).child("/some/path")
    
    They can also be obtained from some convenience functions that construct an
    SSHFileSystem for you, such as connect and from_transport::
    
        f = SSHFile.connect(hostname, username, password)
        f = SSHFile.from_transport(paramiko_transport)
    
    SSHFileSystem instances (to which all SSHFile instance hold a reference)
    wrap their underlying paramiko.Transport instances with an object that
    automatically closes them on garbage collection. There's therefore no need
    to do anything special with an SSHFile when you're done with it, although
    you can use it as a context manager to force its underlying SSHFileSystem
    to close before it's garbage collected.

    SSHFileSystem instances (to which all SSHFile instances hold a reference)
    have a __del__ that automatically closes their underlying
    paramiko.Transport on garbage collection. There's therefore no need to do
    anything special with an SSHFile instance when you're done with it,
    although you can force it to close before it's garbage collected by calling
    self.filesystem.close() on it, or by using it (or its underlying
    SSHFileSystem) as a context manager::
    
        with SSHFile.connect(...) as f:
            ...
    """
    _default_block_size = 2**18 # 256 KB
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
        return SSHFileSystem.connect(host, username, password, port).root
    
    @staticmethod
    def from_transport(transport, autoclose=True):
        return SSHFileSystem(transport, autoclose=autoclose).root
    
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
        self._filesystem.__enter__()
        return self
    
    def __exit__(self, *args):
        self._filesystem.__exit__()
    
    def disconnect(self):
        """
        Note: This function is deprecated, and will be removed in the future.
        Use self.filesystem.close() instead.
        
        Disconnect this SSHFile's underlying connection.
        
        You usually won't need to call this explicitly; connections are
        automatically closed when all SSHFiles referring to them are garbage
        collected. You can use this method to force the connection to
        disconnect before all such references are garbage collected, if you
        want.
        """
        self._filesystem.close()
    
    @property
    def filesystem(self):
        return self._filesystem
    
    @property
    def url(self):
        """
        An ssh:// URL corresponding to the location of this file.
        
        A few important notes:
        
         * If this SSHFile's underlying SSHFileSystem was constructed by
           passing in a paramiko.Transport instance directly, the hostname in
           the resulting URL is only a (well educated) guess as to the remote
           end's IP address. If it was instead constructed via
           SSHFileSystem.connect or SSHFile.connect, the hostname in the
           resulting URL will be the same as that passed to connect().
           
         * The password, if any, given to SSHFile.connect won't be preserved by
           this property as (by design) the password isn't stored anywhere
           after authentication.
           
         * The path of the returned URL will start with two slashes, something
           like ssh://host//path. This prevents it from being interpreted as a
           path relative to the user's home directory by some applications
           (like Mercurial) that interpret paths with only one leading slash as
           such. 
        """
        # This is only a (well educated) guess if our underlying SSHFileSystem
        # was passed a paramiko.Transport directly, but there's not much better
        # we can do.
        return "ssh://{0}/{1}".format(self.filesystem._client_name,
                                     self._path)
    
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


