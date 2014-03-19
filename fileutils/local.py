from fileutils.interface import BaseFile, FileSystem, MountPoint, DiskUsage, Usage
from fileutils.mixins import ChildrenMixin, DefaultMountDevice
from fileutils.constants import FILE, FOLDER, LINK
from fileutils.exceptions import Convert, generate
from fileutils.attributes import ExtendedAttributes, PosixPermissions
from fileutils import exceptions
import os.path
import posixpath
import ntpath
import stat
from contextlib import closing
import zipfile as zip_module
import glob as _glob
import tempfile
import atexit
import urlparse
import urllib
import string
import errno
import subprocess
import re
import traceback

# I'm avoiding dependencies on pywin32 as long as possible... We'll see how
# long I can turn out.
import ctypes

try:
    import xattr
except ImportError:
    xattr = None

# Set of File objects whose delete_on_exit property has been set to True. These
# are deleted by the atexit hook registered two lines down.
_delete_on_exit = set()
@atexit.register
def _():
    for f in _delete_on_exit:
        try:
            f.delete(ignore_missing=True)
        except:
            print "WARNING: Couldn't delete local file {0!r}:".format(f.path)
            traceback.print_exc()


_local_file_system = None

class LocalFileSystem(FileSystem):
    def __new__(cls):
        if _local_file_system:
            # This will double-call _local_file_system.__init__, which isn't a
            # problem since we don't actually override it.
            return _local_file_system
        if os.path is posixpath:
            return object.__new__(PosixLocalFileSystem)
        elif os.path is ntpath:
            return object.__new__(WindowsLocalFileSystem)
        else:
            raise Exception("Unsupported platform")
    
    def child(self, *path_components):
        return File(*path_components)
    
    def cache(self, file_to_cache):
        """
        Copy the specified file or directory (a BaseFile instance) onto the
        local machine in the system temporary directory and return a LocalCache
        instance wrapping the temporary copy, unless it's already a local file,
        in which case a LocalCache wrapping the file itself will be returned.
        
        The returned LocalCache instance can be used as a context manager like
        so::
        
            with LocalFileSystem().cache(some_file) as local_file:
                ...
        
        During the execution of the above block, local_file will be a File
        instance pointing to the local temporary copy of the file. After the
        block exits, the file will be deleted (unless it was already a local
        file, in which case nothing whatsoever will happen).
        
        The file can also be accessed directly from the LocalCache instance's
        location property.
        
        The newly created temporary directory containing the local temporary
        copy of the file will have its delete_on_exit property set to True.
        This allows the file to be passed around without needing to use the
        returned LocalCache instance as a context manager, if you so desire.
        (delete_on_exit will not, of course, be set to True if the file was
        already a local file.)
        """
        if file_to_cache.filesystem == self:
            # Local file
            return LocalCache(None, file_to_cache)
        else:
            # Remote file
            cache = create_temporary_folder(delete_on_exit=True)
            location = file_to_cache.copy_into(cache)
            return LocalCache(cache, location)
    
    def __cmp__(self, other):
        if other is _local_file_system:
            return 0
        else:
            return NotImplemented
    
    def __hash__(self):
        # Should probably return a more random constant here, maybe just let
        # this pass through to object.__hash__
        return 0


class PosixLocalFileSystem(LocalFileSystem):
    @property
    def roots(self):
        return [File("/")]
    
    @property
    def mountpoints(self):
        proc_mounts = File("/proc/self/mountinfo")
        if proc_mounts.exists:
            mountpoints = {}
            with proc_mounts.open("r") as f:
                for line in f:
                    spec = line.split(" ")
                    location = File(spec[4])
                    if location not in mountpoints:
                        mountpoints[location] = (PosixLocalMountPoint(location))
            return list(mountpoints.values())
        return None


class WindowsLocalFileSystem(LocalFileSystem):
    @property
    def roots(self):
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives() #@UndefinedVariable
        for letter in string.uppercase:
            if bitmask & 1:
                drives.append(File(letter + ":\\"))
            bitmask >>= 1
        return drives
    
    @property
    def mountpoints(self):
        return [WindowsMountPoint(r) for r in self.roots]


class LocalMountPoint(MountPoint):
    @property
    def filesystem(self):
        return LocalFileSystem()


class PosixLocalMountPoint(LocalMountPoint):
    def __init__(self, location):
        self._location = location
    
    @property
    def location(self):
        return self._location
    
    @property
    def devices(self):
        proc_mounts = File("/proc/self/mountinfo")
        if proc_mounts.exists:
            devices = []
            with proc_mounts.open("r") as f:
                for line in f:
                    spec = line.split(" ")
                    # 8 = device, 3 = subpath
                    if spec[4] == self.location.path:
                        device = spec[8]
                        subpath = spec[3]
                        location = None
                        if device.startswith('/'):
                            location = File(device)
                        devices.append(DefaultMountDevice(location, device, subpath))
            return devices
        raise Exception("Unsupported platform")        
    
    @property
    def usage(self):
        info = os.statvfs(self.location.path)
        block_size = info.f_frsize
        return DiskUsage(
            space=Usage(
                total=info.f_blocks * block_size,
                used=(info.f_blocks - info.f_bfree) * block_size,
                available=info.f_bavail * block_size
            ),
            inodes=Usage(
                total=info.f_files,
                used=info.f_files - info.f_ffree,
                available=info.f_favail
            )
        )
    
    def unmount(self, force=False):
        """
        Unmount this mountpoint.
        
        If force is True, -f will be passed to the umount call. This will
        (among other things) force nonresponsive NFS mounts to unmount, as well
        as forcing mounts not listed in /etc/mtab to unmount.
        """
        command = ['umount', self.location.path]
        if force:
            command.append('-f')
        subprocess.check_call(command)
    
    def __str__(self):
        return "<PosixLocalMountPoint {0!r}>".format(self._location.path)
    
    __repr__ = __str__


class WindowsMountPoint(LocalMountPoint):
    def __init__(self, location):
        self._location = location


_local_file_system = LocalFileSystem()


class PosixLocalExtendedAttributes(ExtendedAttributes):
    # Python 3.3 added native extended attribute support in the form of
    # os.listxattr and family. When fileutils gains Python 3 compatibility, we
    # should use os.listxattr and family if they exist.
    def __init__(self, f):
        self._file = f
        self._path = f.path
    
    def get(self, name):
        try:
            return xattr.getxattr(self._path, name)
        except IOError as e:
            # TODO: See if this is different on other platforms, such as OS X
            if (e.errno == errno.ENODATA or e.errno == errno.EOPNOTSUPP
                    or e.errno == errno.ENOENT):
                raise KeyError(name)
            else:
                raise
    
    def set(self, name, value):
        # This can bail with EOPNOTSUPP if the user specifies attribute names
        # we don't like. Should we warn the user about this?
        xattr.setxattr(self._path, name, value)
    
    def list(self):
        try:
            return list(xattr.listxattr(self._path))
        except IOError as e:
            if e.errno == errno.EOPNOTSUPP or e.errno == errno.ENOENT: # No
                # xattr support or the file doesn't exist
                return []
            else:
                raise
    
    def delete(self, name):
        try:
            xattr.removexattr(self._path, name)
        except IOError as e:
            if (e.errno == errno.ENODATA or e.errno == errno.EOPNOTSUPP
                    or e.errno == errno.ENOENT):
                raise KeyError(name)
            else:
                raise
    
    def __repr__(self):
        return "<PosixLocalExtendedAttributes for {0!r}>".format(self._file)
    
    __str__ = __repr__


class PosixLocalPermissions(PosixPermissions):
    def __init__(self, f):
        self._file = f
    
    @property
    def mode(self):
        return os.stat(self._file.path).st_mode
    
    @mode.setter
    def mode(self, value):
        # This is racy in the face of the underlying file being replaced with a
        # symlink, but, as Linux doesn't provide lchmod, I'm not sure there's
        # a better way to do this... Patches welcome.
        if not self._file.is_link:
            os.chmod(self._file.path, value)
    
    def __repr__(self):
        return "<PosixLocalPermissions for {0!r}>".format(self._file)
    
    __str__ = __repr__


class LocalCache(object):
    """
    An object representing a remote file that's been cached locally.
    These can be obtained from LocalFileSystem.cache(). See that method's
    docstring for more information.
    """
    def __init__(self, cache, location):
        self._cache = cache
        self._location = location
    
    @property
    def location(self):
        """
        The local temporary file or directory, as a BaseFile object. This file
        contains the same data as the remote file passed into
        LocalFileSystem.cache(). It also has the same name.
        """
        return self._location
    
    @property
    def cache(self):
        """
        The temporary directory created to contain the local temporary file, or
        None if the file was already a local file. This is the directory that
        will be deleted by self.__exit__.
        """
        return self._cache
    
    def __enter__(self):
        return self.location
    
    def __exit__(self, *args):
        if self._cache:
            self._cache.delete()
            self._cache.delete_on_exit = False


class File(ChildrenMixin, BaseFile):
    """
    An object representing a file or folder on the local filesystem. File
    objects are intended to be as opaque as possible; one should rarely, if
    ever, need to know about the pathname of a File object, or that a File even
    has a pathname associated with it.
    
    The file or folder referred to by a File object need not exist. One can
    test whether a File object represents a file that does exist using the
    exists property.
    
    File objects cannot be changed to refer to a different file after they are
    created.
    """
    _sep = os.path.sep
    attributes = None
    
    def __new__(cls, *args):
        if os.path is posixpath:
            return object.__new__(PosixFile)
        elif os.path is ntpath:
            return object.__new__(WindowsFile)
        else:
            raise Exception("Unsupported platform")
    
    def __init__(self, *path_components):
        r"""
        Creates a new file from the specified path components. Each component
        represents the name of a folder or a file. These are internally joined
        as if by os.path.join(*path_components).
        
        It's also possible, although not recommended, to pass a full pathname
        (in the operating system's native format) into File. On Windows, one
        could therefore do File(r"C:\some\file"), and File("/some/file") on
        Linux and other Unix operating systems.
        
        You can also call File(File(...)). This is equivalent to File(...) and
        exists to make it easier for functions to accept either a pathname or
        a File object.
        
        Passing no arguments (i.e. File()) results in a file that refers to the
        working directory as of the time the File instance was constructed.
        
        Pathnames are internally stored in absolute form; as a result, changing
        the working directory after creating a File instance will not change
        the file referred to.
        """
        # If we're passed a File object, use its path
        if path_components and isinstance(path_components[0], File):
            path = path_components[0]._path
        # Join the path components, or use the empty string if there are none
        elif path_components:
            path = os.path.join(*path_components)
        else:
            path = ""
        # Make the pathname absolute
        path = self._resolve_path(path)
        self._path = path
        
        self.attributes = {}
    
    @staticmethod
    def _resolve_path(path):
        return os.path.abspath(path)
    
    def child(self, *names):
        return File(os.path.join(self.path, *names))

    @property
    def parent(self):
        dirname = os.path.dirname(self._path)
        # I don't remember at the moment how this works on Windows, so cover
        # all the bases until I can test it out
        if dirname is None or dirname == "":
            return None
        f = File(dirname)
        # Linux returns the same file from dirname
        if f == self:
            return None
        return f
    
    @property
    def filesystem(self):
        return LocalFileSystem()
    
    @property
    def mountpoint(self):
        # Build up a mountpoint dictionary
        mountpoints = self.filesystem.mountpoints
        if mountpoints is None:
            return None
        mountpoint_dict = dict((m.location, m)
                               for m in mountpoints)
        for f in self.get_ancestors(including_self=True):
            try:
                return mountpoint_dict[f]
            except KeyError:
                pass

    def get_path_components(self, relative_to=None):
        if relative_to is None:
            return self._path.split(os.path.sep)
        else:
            return os.path.relpath(self._path, File(relative_to)._path).split(os.sep)
    
    @property
    def url(self):
        return urlparse.urljoin("file:", urllib.pathname2url(self._path))

    @property
    def child_names(self):
        if not self.is_folder:
            return
        return sorted(os.listdir(self._path))
    
    @property
    def type(self):
        try:
            mode = os.lstat(self.path).st_mode
        except os.error: # File doesn't exist
            return None
        if stat.S_ISREG(mode):
            return FILE
        if stat.S_ISDIR(mode):
            return FOLDER
        if stat.S_ISLNK(mode):
            return LINK
        return "fileutils.OTHER"

    @property
    def link_target(self):
        """
        Returns the target to which this file, which is expected to be a
        symbolic link, points, as a string. If this file is not a symbolic
        link, None is returned.
        """
        if not self.is_link:
            return None
        return os.readlink(self._path)
    
    def open_for_reading(self):
        # TODO: Consider wrapping with a stream that produces new-style
        # exceptions as well... Also consider splitting such a thing out
        # into its own library that can wrap sockets etc.
        return self.open("rb")

    @property
    def size(self):
        """
        The size, in bytes, of this file. This is the number of bytes that the
        file contains; the number of actual bytes of disk space it consumes is
        usually larger.
        
        If this file is actually a folder, the sizes of its child files and
        folders will be recursively summed up and returned. This can take quite
        some time for large folders.
        """
        if self.is_folder:
            return sum(f.size for f in self.children)
        elif self.is_file:
            return os.path.getsize(self.path)
        else: # Broken symbolic link or some other type of file
            return 0

    def change_to(self):
        """
        Sets the current working directory to self.
        
        Since File instances internally store paths in absolute form, other
        File instances will continue to work just fine after this is called.
        
        If you need to restore the working directory at any point, you might
        want to consider using :obj:`self.as_working <as_working>` instead.
        """
        os.chdir(self.path)

    def create_folder(self, ignore_existing=False, recursive=False):
        """
        Creates the folder referred to by this File object. If it already
        exists but is not a folder, an exception will be thrown. If it already
        exists and is a folder, an exception will be thrown if ignore_existing
        is False (the default); if ignore_existing is True, no exception will
        be thrown.
        
        If the to-be-created folder's parent does not exist and recursive is
        False, an exception will be thrown. If recursive is True, the folder's
        parent, its parent's parent, and so on will be created automatically.
        """
        # See if we're already a folder
        if self.is_folder:
            # We are. If ignore_existing is True, then just return.
            if ignore_existing:
                return
            # If it's not, raise an exception. TODO: EAFP
            else:
                raise generate(exceptions.FileExistsError, self)
        else:
            # We're not a folder. (We don't need to see if we already exist as
            # e.g. a file as the call to os.mkdir will take care of raising an
            # exception for us in such a case.) Now create our parent if it
            # doesn't exist and recursive is True.
            if recursive and self.parent and not self.parent.exists:
                self.parent.create_folder(recursive=True)
            # Now turn ourselves into a folder.
            os.mkdir(self.path)

    def delete(self, contents=False, ignore_missing=False):
        # If it's a mount point, unmount it before trying to delete it
        while self.is_mount:
            self.mountpoint.unmount(force=True)
        if not self.exists:
            if not ignore_missing:
                raise generate(exceptions.FileNotFoundError, self)
        elif self.is_folder and not self.is_link:
            for child in self.children:
                child.delete()
            os.rmdir(self.path)
        else:
            os.remove(self._path)

    def link_to(self, other):
        """
        Creates this file as a symbolic link pointing to other, which can be
        a pathname or a File object. Note that if it's a pathname, a symbolic
        link will be created with the exact path specified; it will therefore
        be absolute if the path is absolute or relative (to the link itself) if
        the path is relative. If a File object, however, is used, the symbolic
        link will always be absolute.
        """
        if isinstance(other, File):
            os.symlink(other.path, self._path)
        else:
            os.symlink(other, self._path)
    
    def open_for_writing(self, append=False):
        if append:
            return self.open("ab")
        else:
            return self.open("wb")
    
    def open(self, *args, **kwargs):
        with Convert():
            return open(self._path, *args, **kwargs)

    def rename_to(self, other):
        if isinstance(other, File):
            with Convert():
                os.rename(self._path, other.path)
        else:
            BaseFile.rename_to(self, other)
    
    def glob(self, glob):
        """
        Expands the specified path relative to self and returns a list of all
        matching files, as File objects. This is a thin wrapper around a call
        to Python's glob.glob function.
        """
        return [File(f) for f in _glob.glob(os.path.join(self.path, glob))]
    
    def zip_into(self, filename, contents=True):
        """
        Creates a zip archive of this folder and writes it to the specified
        filename, which can be either a pathname or a File object.
        
        If contents is True (the default), the files (and folders, and so on
        recursively) contained within this folder will be written directly to
        the zip file. If it's False, the folder will be written itself. The
        difference is that, given a folder foo which looks like this::
        
            foo/
                bar
                baz/
                    qux
        
        Specifying contents=False will result in a zip file whose contents look
        something like::
        
            zipfile.zip/
                foo/
                    bar
                    baz/
                        qux
        
        Whereas specifying contents=True will result in this::
        
            zipfile.zip/
                bar
                baz/
                    qux
        
        NOTE: This has only been tested on Linux. I still need to test it on
        Windows to make sure pathnames are being handled correctly.
        """
        with closing(zip_module.ZipFile(File(filename).path, "w")) as zipfile:
            for f in self.recurse():
                if contents:
                    path_in_zip = f.relative_path(self)
                else:
                    path_in_zip = f.relative_path(self.parent)
                zipfile.write(f.path, path_in_zip)
        
    def unzip_into(self, folder):
        """
        Unzips the zip file referred to by self into the specified folder,
        which will be automatically created (as if by File(folder).mkdirs())
        if it does not yet exist.
        
        NOTE: This is an unsafe operation! The same warning present on Python's
        zipfile.ZipFile.extractall applies here, namely that a maliciously
        crafted zip file could cause absolute filesystem paths to be
        overwritten. I hope to hand-roll my own extraction code in the future
        that will explicitly filter out absolute paths.
        
        The return value of this function is File(folder).
        """
        folder = File(folder)
        folder.mkdirs(silent=True)
        with closing(zip_module.ZipFile(self._path, "r")) as zipfile:
            zipfile.extractall(folder.path)

    @property
    def delete_on_exit(self):
        """
        A boolean indicating whether or not this file (which may be a file or a
        folder) should be deleted on interpreter shutdown. This is False by
        default, but may be set to True to request that a particular file be
        deleted on exit, and potentially set back to False to cancel such a
        request.
        
        Note that such files are not absolutely guaranteed to be deleted on
        exit. Deletion is handled via an :obj:`atexit` hook, so files will not be
        deleted if, for example, the interpreter crashes or os._exit() is
        called.
        
        The value of this property is shared among all File instances pointing
        to a given path. For example::
        
            File("test").delete_on_exit = True # Instance 1
            print File("test").delete_on_exit # Instance 2, prints "True"
        """
        return self in _delete_on_exit
    
    @delete_on_exit.setter
    def delete_on_exit(self, value):
        if value:
            _delete_on_exit.add(self)
        else:
            _delete_on_exit.discard(self)

    # Use __cmp__ instead of the rich comparison operators for brevity
    def __cmp__(self, other):
        if not isinstance(other, File):
            return NotImplemented
        return cmp(os.path.normcase(self.path), os.path.normcase(other.path))
    
    def __hash__(self):
        return hash(os.path.normcase(self.path))
    
    def __nonzero__(self):
        """
        Returns True. File objects are always true values; to test for their
        existence, use self.exists instead.
        """
        return True


class PosixFile(File):
    def __init__(self, *args, **kwargs):
        File.__init__(self, *args, **kwargs)
        
        self.attributes[PosixPermissions] = PosixLocalPermissions(self)
        if xattr:
            self.attributes[ExtendedAttributes] = PosixLocalExtendedAttributes(self)
    
    @staticmethod
    def _resolve_path(path):
        # Strip off double leading slashes
        while path[0:2] == '//':
            path = path[1:]
        return File._resolve_path(path)
        
    def __str__(self):
        return "fileutils.PosixFile(%r)" % self._path
    
    __repr__ = __str__


class WindowsFile(File):
    @staticmethod
    def _resolve_path(path):
        # If it looks like a path with a drive letter that has leading slashes
        # (most likely as artifacts from URL parsing), strip them off. Windows
        # doesn't allow colons in paths, so this won't ever mistakenly strip
        # off slashes.
        if re.match('^/+[a-zA-Z]:', path):
            path = path.lstrip('/')
        return File._resolve_path(path)
    
    def __str__(self):
        return "fileutils.WindowsFile(%r)" % self._path
    
    __repr__ = __str__


# Alias in preparation for the eventual rename of File to LocalFile
LocalFile = File


def create_temporary_folder(suffix="", prefix="tmp", parent=None,
                            delete_on_exit=False):
    """
    Creates a folder (with tmpfile.mkdtemp) with the specified prefix, suffix,
    and parent folder (or the current platform's default temporary directory if
    no parent is specified) and returns a File object pointing to it.
    
    If delete_on_exit is True, the returned file's delete_on_exit property will
    be set to True just before returning it.
    """
    parent = File(parent or tempfile.gettempdir())
    folder = File(tempfile.mkdtemp(suffix, prefix, parent.path))
    folder.delete_on_exit = delete_on_exit
    return folder
