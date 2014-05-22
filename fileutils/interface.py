"""
Abstract classes.

This module contains all of the abstract classes that define the public API for
fileutils.
"""

from abc import ABCMeta, abstractmethod, abstractproperty
from fileutils.constants import FILE, FOLDER, LINK, YIELD, RECURSE
from fileutils.exceptions import generate
from fileutils import exceptions
import hashlib
import collections
import string
import random
import tempfile

__all__ = ["FileSystem", "MountPoint", "MountDevice", "DiskUsage", "Usage",
           "BaseFile"]

class DiskUsage(object):
    """
    Disk space and inode usage.
    
    Instances of this class are typically obtained from
    :obj:`MountPoint.usage`.
    """
    def __init__(self, space, inodes):
        self._space = space
        self._inodes = inodes
    
    @property
    def space(self):
        """
        An instance of :obj:`Usage` indicating utilization of disk space.
        """
        return self._space
    
    @property
    def inodes(self):
        """
        An instance of :obj:`Usage` indicating utilization of inodes, or None
        on platforms (like Windows) that don't have such a concept.
        """
        return self._inodes
    
    def __repr__(self):
        return "DiskUsage(space={0!r}, inodes={1!r})".format(self.space, self.inodes)
    
    __str__ = __repr__


class Usage(object):
    """
    Usage of a particular file system resource, such as disk space (given in
    bytes) or inodes.
    """
    def __init__(self, total, used, available):
        self._total = total
        self._used = used
        self._available = available
    
    @property
    def total(self):
        """
        Total amount of disk space or inodes available.
        """
        return self._total
    
    @property
    def used(self):
        """
        Amount of disk space or number of inodes currently in use.
        """
        return self._used
    
    @property
    def available(self):
        """
        Amount of free disk space or number of inodes available to the current
        user.
        
        This is often the same as :obj:`self.free <free>`, but things like disk
        space quotas and blocks reserved for the superuser can make it have a
        value less than that of self.free.
        """
        return self._available
    
    @property
    def free(self):
        """
        Amount of disk space or number of inodes not currently in use.
        """
        return self.total - self.used
    
    def __repr__(self):
        return "Usage(total={0!r}, used={1!r}, available={2!r})".format(self.total, self.used, self.available)


class FileSystem(object):
    """
    An abstract class representing an entire file system hierarchy.
    
    Instances of this class are typically obtained by directly instantiating
    its subclasses. The most commonly used subclass,
    :obj:`LocalFileSystem <fileutils.local.LocalFileSystem>`, maintains
    a singleton instance that corresponds to the filesystem of the local
    machine. Other subclasses include
    :obj:`SSHFileSystem <fileutils.ssh.SSHFileSystem>`.
    """
    def child(self, path):
        """
        Return an instance of :obj:`BaseFile` representing the file located at
        the specific path. 
        """
        raise NotImplementedError
    
    @property
    def roots(self):
        """
        A list of all of the file system hierarchy roots exposes by this
        FileSystem instance, as :obj:`BaseFile` instances.
        
        On Windows, there will be one root per drive letter. On POSIX systems,
        there will be exactly one root, namely '/'.
        """
        raise NotImplementedError
    
    @property
    def root(self):
        """
        A sensible "default" root for this file system, or None if there isn't
        really any sensible default.
        
        The default implementation just returns self.roots[0].
        """
        return self.roots[0]
    
    @property
    def mountpoints(self):
        """
        A list of :obj:`MountPoint` instances corresponding to all mount points
        on the system.
        
        On Windows, there will be exactly one mount point for each drive
        letter. On POSIX systems, there will be one mount point per, well,
        mount point.
        
        FileSystem implementations like URLFileSystem that don't support a
        proper notion of mount points are permitted to return None from this
        function.
        
        The default implementation of this method just returns None.
        """
        return None
    
    @property
    def temporary_directory(self):
        """
        A :obj:`BaseFile` instance pointing to a directory on this file system
        in which temporary files and directories can be placed, or None if this
        file system exposes no such directory.
        
        LocalFileSystem and SSHFileSystem all expose a temporary directory;
        only file systems like FTPFileSystem and URLFileSystem do not.
        """
        return None


class MountPoint(object):
    """
    An abstract class representing mount points on a file system.
    
    Instances of this class can be obtained from :obj:`~BaseFile.mountpoint`, a
    property that returns the MountPoint instance on which the file in question
    resides. They can also be obtained from :obj:`~FileSystem.mountpoints`, a
    property that returns a list of all of the system's mount points.
    """
    @property
    def filesystem(self):
        """
        The :obj:`FileSystem` instance on which this mount point resides.
        """
        raise NotImplementedError
    
    @property
    def location(self):
        """
        The :obj:`BaseFile` instance indicating the directory at which this
        mount point is mounted.
        """
        return None
    
    @property
    def devices(self):
        """
        A list of instances of :obj:`MountDevice` representing all of the
        devices currently mounted at this mount point, in the order in which
        they were attached. The last of these is the device whose data is
        currently available at this mount point.
        
        Not all systems support stacks of devices mounted at the same
        mount point. For systems that don't support this, there will never be
        more than one device mounted at any given mount point. For systems that
        do (such as Linux), unmounting a mount point simply causes the last
        device attached to the mount point to be popped off the stack, and the
        next device's data is made available at that mount point.
        """
        return []
    
    @property
    def device(self):
        """
        An instance of :obj:`MountDevice` representing the topmost device
        currently mounted at this mount point. This is the device whose data is
        currently available at this mount point.
        
        This is just short for :obj:`self.devices <devices>`[-1], but if
        self.devices is empty, None will be returned instead.
        """
        devices = self.devices
        if devices:
            return self.devices[-1]
        else:
            return None
    
    @property
    def usage(self):
        """
        An instance of :obj:`DiskUsage` indicating the current disk and inode
        usage for this mount point, or None if this MountPoint implementation
        does not expose disk usage information.
        """
        return None
    
    def unmount(self, force=True):
        """
        Unmount the device whose data is currently visible at this mount point.
        """
        raise NotImplementedError
    
    umount = unmount
    
    @property
    def total_space(self):
        r"""
        Shorthand for self.\ :obj:`usage <usage>`.\ :obj:`space <DiskUsage.space>`.\ :obj:`total <Usage.total>`.
        """
        return self.usage and self.usage.space.total
    
    @property
    def used_space(self):
        r"""
        Shorthand for self.\ :obj:`usage <usage>`.\ :obj:`space <DiskUsage.space>`.\ :obj:`used <Usage.used>`.
        """
        return self.usage and self.usage.space.used
    
    @property
    def available_space(self):
        r"""
        Shorthand for self.\ :obj:`usage <usage>`.\ :obj:`space <DiskUsage.space>`.\ :obj:`available <Usage.available>`.
        """
        return self.usage and self.usage.space.available
    
    @property
    def free_space(self):
        r"""
        Shorthand for self.\ :obj:`usage <usage>`.\ :obj:`space <DiskUsage.space>`.\ :obj:`free <Usage.free>`.
        """
        return self.usage and self.usage.space.free


class MountDevice(object):
    """
    A device as mounted under a particular mount point.
    
    Note: The API of this class is still in flux. I'm particularly considering
    splitting it into two classes whose names are yet to be decided, one of
    which will contain every property except subpath and the other of which
    will contain two properties, subpath and device, the latter pointing to an
    instance of the former class. Bear this in mind when writing code that uses
    this class.
    """
    @property
    def location(self):
        """
        The location of this device as a :obj:`BaseFile` instance, if the subclass
        exposes mount point devices in the form of a file in the file system
        hierarchy. On Linux, for example, this might be something like
        File('/dev/sda1'). On Windows this will be None, and it will also be
        None on Linux for special file systems like tmpfs that don't have any
        representation in the file system hierarchy.
        """
        raise NotImplementedError
    
    @property
    def device(self):
        """
        A textual representation of this device, if the subclass exposes such
        information.
        
        If :obj:`self.location <location>` is not None, this will be
        self.location.path.
        
        On Linux, for special file system types, this will be the name of the
        type in question; 'tmpfs', for example.
        """
        raise NotImplementedError
    
    @property
    def subpath(self):
        """
        The subpath, as a string containing an absolute path, of the file
        system located on this device being exposed to the mount point on which
        this device is mounted, or None if the subclass doesn't support such a
        notion.
        
        For most mount devices that support this, this will just be "/". It can
        be a different path when a nested path within a particular file system
        is exposed with a bind mount; in such a case, this is the path within
        the file system being exposed at the mount point on which this device
        is mounted.
        """
        raise NotImplementedError


class BaseFile(object):
    """
    An abstract class representing an absolute path to a file on a particular
    FileSystem instance.
    
    Instances of this class can be obtained from
    :obj:`FileSystem.child()` <FileSystem.child>`. They can also be obtained
    from :obj:`FileSystem.roots`, a property providing a list of all
    of the file system's root directories.
    """
    _default_block_size = 16384
    
    def child(self, *names):
        """
        Returns a file object representing the child of this file with the
        specified name. If multiple names are present, they will be joined
        together. If no names are present, self will be returned.
        
        If any names are absolute, all names before them (and self) will be
        discarded. Relative names (like "..") are also allowed. If you want a
        method that guarantees that the result is a child of self, use
        self.safe_child(...).
        
        This method is analogous to
        :obj:`os.path.join(self.path, *names) <os.path.join>`.
        """
        raise NotImplementedError
    
    @property
    def parent(self):
        """
        Returns a file representing the parent of this file. If this file has
        no parent (for example, if it's "/" on Unix-based operating systems or
        a drive letter on Windows), None will be returned.
        """
        raise NotImplementedError
    
    @property
    def mountpoint(self):
        """
        The MountPoint instance on which this file resides, or None if this
        file is an instance of a class like URL that doesn't support mount
        points.
        
        The default implementation of this method just returns None.
        """
        return None
    
    def get_path_components(self, relative_to=None):
        """
        Returns a list of the components in this file's path, including (on
        POSIX-compliant systems) an empty leading component for absolute paths.
        
        If relative_to is specified, the returned set of components will
        represent a relative path, the path of this file relative to the
        specified one. Otherwise, the returned components will represent an
        absolute path.
        """
        raise NotImplementedError
    
    def same_as(self, other):
        """
        Returns True if this file represents the same file as the specified
        one, False otherwise.
        
        This is usually the same as self == other, but URL implements this
        differently: a URL with a trailing slash and a URL without are treated
        as the same by same_as but different by ==.
        
        The default implementation returns True if self.path_components ==
        other.path_components and type(self) == type(other), or False otherwise.
         
        """
        # True if self' and other's paths mean the same thing, false if they
        # don't. Mainly useful for URLs, where the idea is that, given:
        #
        # a = URL("http://foo/a")
        # b = URL("http://foo/a/")
        # 
        # a == b is False, but a.same_as(b) is True. Can be overridden by
        # subclasses as needed to implement this sort of logic.
        if type(self) != type(other):
            return False
        return self.path_components == other.path_components
    
    def safe_child(self, *names):
        """
        Same as self.child(*names), but checks that the resulting file is a
        descendant of self. If it's not, an exception will be thrown. This
        allows unsanitized paths to be used without fear that things like ".."
        will be used to escape the confines of self.
        
        The pathname may contain occurrences of ".." so long as they do not
        escape self. For example, "a/b/../c" is perfectly fine, but "a/../.."
        is not.
        """
        child = self.child(*names)
        if not self.ancestor_of(child):
            raise ValueError("Names %r escape the parent %r" % (names, self))
        return child
    
    def __div__(self, other):
        """
        An absolutely pointless and unnecessary alias for self.child(other)
        that exists solely because I was overly bored one night while working
        on fileutils.
        """
        return self.child(other)

    def sibling(self, *names):
        """
        Returns a File object representing the sibling of this file with the
        specified name. This is equivalent to self.parent.child(name).
        """
        return self.parent.child(*names)
    
    def get_ancestors(self, including_self=False):
        """
        Returns a list of all of the ancestors of this file, with self.parent
        first. If including_self is True, self will be first, self.parent will
        be second, and so on.
        """
        if including_self:
            current = self
        else:
            current = self.parent
        results = []
        while current is not None:
            results.append(current)
            current = current.parent
        return results

    @property
    def ancestors(self):
        """
        A list of all of the ancestors of this file, with self.parent first.
        
        This property simply returns
        :obj:`self.get_ancestors() <get_ancestors>`. Have a look at that
        method if you need to do more complex things like include self as one
        of the returned ancestors.
        """
        return self.get_ancestors()

    def descendant_of(self, other, including_self=False):
        """
        Returns true if this file is a descendant of the specified file. This
        is equivalent to other.ancestor_of(self, including_self).
        """
        for ancestor in self.get_ancestors(including_self):
            if other.same_as(ancestor):
                return True
        return False

    def ancestor_of(self, other, including_self=False):
        """
        Returns true if this file is an ancestor of the specified file. A file
        is an ancestor of another file if that other file's parent is (as
        decided by :obj:`~same_as`) this file, or its parent's parent is this
        file, and so on.
        
        If including_self is True, the file is considered to be an ancestor of
        itself, i.e. True will be returned in the case that self.same_as(other).
        Otherwise, only the file's immediate parent, and its parent's parent,
        and so on are considered to be ancestors.
        """
        return other.descendant_of(self, including_self)

    def get_path(self, relative_to=None, separator=None):
        """
        Gets the path to the file represented by this File object.
        
        If relative_to is specified, the returned path will be a relative path,
        the path of this file relative to the specified one. Otherwise, the
        returned path will be absolute.
        
        If separator (which must be a string) is specified, it will be used as
        the separator to place between path components in the returned path.
        Otherwise, os.path.sep will be used as the separator.
        """
        if separator is None:
            separator = self._sep
        return separator.join(self.get_path_components(relative_to))

    @property
    def path(self):
        """
        The absolute path to the file represented by this file object, in a
        format native to the type of file in use. For instances of
        fileutils.local.File, this pathname can be used with Python's
        traditional file-related utilities.
        
        This property simply returns self.get_path(). See the documentation for
        that method for more complex ways of creating paths (including
        obtaining relative paths).
        """
        return self.get_path()

    @property
    def path_components(self):
        """
        A property that simply returns
        :obj:`self.get_path_components() <get_path_components>`.
        """
        return self.get_path_components()

    @property
    def name(self):
        """
        The name of this file. For example, File("a", "b", "c").name will be
        "c".
        
        On Unix-based operating systems, File("/").name will be the empty
        string.
        """
        return self.path_components[-1]
    
    @property
    def type(self):
        """
        The type of this file. This can be one of FILE, FOLDER, or LINK (I
        don't yet have constants for block/character special devices; those
        will come soon.) If the file does not exist, this should be None.
        """
        raise NotImplementedError
    
    @property
    def link_target(self):
        """
        Returns the target to which this file, which is expected to be a
        symbolic link, points, as a string. If this file is not a symbolic
        link, None is returned.
        
        Subclasses (such as URL) without a well-defined notion of symbolic
        links are free to interpret this as they wish; URL, for example,
        presents as a link any URL which sends back an HTTP redirect.
        """
        raise NotImplementedError
    
    def open_for_reading(self):
        """
        Open this file for reading in binary mode and return a Python file-like
        object from which this file's contents can be read.
        """
        # Should open in "rb" mode
        raise NotImplementedError

    @property
    def size(self):
        """
        The size, in bytes, of this file. This is the number of bytes that the
        file contains; the number of actual bytes of disk space it consumes is
        usually larger.
        
        If this file is actually a folder, the sizes of its child files and
        folders will be recursively summed up and returned. This can take quite
        some time for large folders.
        
        This is the same as len(self).
        """
        raise NotImplementedError
    
    @property
    def exists(self):
        """
        True if this file/folder exists, False if it doesn't. This will be True
        even for broken symbolic links; use self.valid if you want an
        alternative that returns False for broken symbolic links.
        """
        return self.type is not None

    @property
    def valid(self):
        """
        True if this file/folder exists, False if it doesn't. This will be
        False for broken symbolic links; use self.exists if you want an
        alternative that returns True for broken symbolic links.
        """
        return self.dereference(True).exists
    
    @property
    def is_broken(self):
        """
        True if this File is a symbolic link that is broken, False if it isn't.
        A symbolic link that points to a broken symbolic link is itself
        considered to be broken.
        """
        return self.is_link and not self.dereference(True).exists
    
    @property
    def is_file(self):
        """
        True if this File is a file, False if it isn't. If the file/folder
        doesn't actually exist yet, this will be False.
        
        If this file is a symbolic link that points to a file, this will be
        True.
        """
        return self.dereference(True).type is FILE
    
    @property
    def is_folder(self):
        """
        True if this File is a folder, False if it isn't. If the file/folder
        doesn't actually exist yet, this will be False.
        
        If this file is a symbolic link that points to a folder, this will be
        True.
        """
        return self.dereference(True).type is FOLDER
    
    @property
    def is_directory(self):
        """
        Same as self.is_folder.
        """
        return self.is_folder
    
    @property
    def is_link(self):
        """
        True if this File is a symbolic link, False if it isn't. This will be
        True even for broken symbolic links.
        """
        return self.type is LINK
    
    @property
    def is_mount(self):
        """
        True if this File is a mount point, False if it isn't.
        
        This is just short for self.mountpoint.location == self, but with a
        check to ensure that self.mountpoint.location is not None.
        """
        mountpoint = self.mountpoint
        if mountpoint is None:
            return False
        return self.mountpoint.location == self
    
    def check_folder(self):
        """
        Checks to see whether this File refers to a folder. If it doesn't, an
        exception will be thrown.
        """
        if not self.is_folder:
            raise generate(exceptions.NotADirectoryError, self)
    
    def check_file(self):
        """
        Checks to see whether this File refers to a file. If it doesn't, an
        exception will be thrown.
        """
        if not self.is_file:
            raise generate(exceptions.FileNotFoundError, self)
    
    def copy_to(self, other, overwrite=False, dereference_links=True,
                which_attributes={}):
        """
        Copies the contents and attributes of this file or directory to the
        specified file. An exception will be thrown if the specified file
        already exists and overwrite is False.
        
        If dereference_links is True (the default), symbolic links encountered
        during copying will be dereferenced and their targets copied in their
        place. If dereference_links is False, such links will be recreated
        purely as symbolic links. Note that this could render some symbolic
        links broken.
        
        which_attributes is a dictionary indicating which attributes are to be
        copied, in the same format as that given to :obj:`copy_attributes_to`\ .
        """
        # If self.is_folder is True, requires isinstance(self, Listable) and
        # isinstance(other, Hierarchy) when we implement support for folders.
        # Requires isinstance(other, Writable) always.
        
        # TODO: Use (and catch or pass on) proper exceptions here, EAFP style
        if other.exists:
            if overwrite:
                other.delete()
            else:
                raise generate(exceptions.FileExistsError, other)
        if dereference_links:
            source = self.dereference(True)
        else:
            source = self
        file_type = source.type
        if file_type is FILE:
            with other.open_for_writing() as write_to:
                for block in self.read_blocks():
                    write_to.write(block)
        elif file_type is FOLDER:
            other.create_folder()
            for child in self.children:
                child.copy_into(other, dereference_links=dereference_links,
                                which_attributes=which_attributes)
        elif file_type is LINK:
            other.link_to(self.link_target)
        elif file_type is None:
            # TODO: This will happen when we're dereferencing links and we
            # find one that doesn't exist. Should we just ignore such a
            # situation and not copy anything, or should we copy the broken
            # link itself?
            raise generate(exceptions.FileNotFoundError, source)
        else:
            raise NotImplementedError(str(self))
        source.copy_attributes_to(other, which_attributes=which_attributes)

    def copy_into(self, other, overwrite=False, dereference_links=True,
                  which_attributes={}):
        """
        Copies this file to an identically named file inside the specified
        folder. This is just shorthand for self.copy_to(other.child(self.name))
        which, from experience, seems to be by far the most common use case for
        the copy_to function.
        
        The newly-created file in the specified folder will be returned as per
        other.child(self.name).
        
        overwrite, dereference_links, and which_attributes have the same
        meanings as their respective arguments given to copy_to.
        """
        new_file = other.child(self.name)
        self.copy_to(new_file, overwrite, dereference_links, which_attributes)
        return new_file

    def dereference(self, recursive=False):
        """
        Dereference the symbolic link represented by this file and return a
        File object pointing to the symbolic link's referent.
        
        If recursive is False, a File object pointing directly to the referent
        will be returned. If recursive is True, the referent itself will be
        recursively dereferenced, and the returned File will be guaranteed not
        to be a link.
        
        If this file is not a symbolic link, self will be returned.
        """
        if not self.is_link:
            return self
        # Resolve the link relative to its parent in case it points to a
        # relative path
        target = self.parent.child(self.link_target)
        if recursive:
            return target.dereference(recursive=True)
        else:
            return target

    def hash(self, algorithm=hashlib.md5, return_hex=True):
        """
        Compute the hash of this file and return it, as a hexidecimal string.
        
        The default algorithm is md5. An alternate constructor from hashlib
        can be passed as the algorithm parameter; file.hash(hashlib.sha1)
        would, for example, compute the SHA-1 hash instead.
        
        If return_hex is False (it defaults to True), the hash object itself
        will be returned instead of the return value of its hexdigest() method.
        One can use this to access the binary hash instead.
        """
        hasher = algorithm()
        for block in self.read_blocks():
            hasher.update(block)
        if return_hex:
            hasher = hasher.hexdigest()
        return hasher
    
    def read_blocks(self, block_size=None):
        """
        A generator that yields successive blocks of data from this file. Each
        block will be no larger than block_size bytes, which defaults to 16384.
        This is useful when reading/processing files larger than would
        otherwise fit into memory.
        
        One could implement, for example, a copy function thus::
        
            with target.open("wb") as target_stream:
                for block in source.read_blocks():
                    target_stream.write(block)
        """
        if block_size is None:
            block_size = self._default_block_size
        with self.open_for_reading() as f:
            data = f.read(block_size)
            while data:
                yield data
                data = f.read(block_size)

    def read(self):
        """
        Read the contents of this file and return them as a string. This is
        usually a bad idea if the file in question is large, as the entire
        contents of the file will be loaded into memory.
        """
        with self.open_for_reading() as f:
            return f.read()

    @property
    def children(self):
        """
        A list of all of the children of this file, as a list of File objects.
        If this file is not a folder, the value of this property is None.
        """
        raise NotImplementedError
    
    @property
    def child_names(self):
        """
        A list of the names of all of the children of this file, as a list of
        strings. If this file is not a folder, the value of this property is
        None.
        """
        raise NotImplementedError

    def recurse(self, filter=None, include_self=True, recurse_skipped=True):
        """
        A generator that recursively yields all child File objects of this file.
        Files and directories (and the files and directories contained within
        them, and so on) are all included.
        
        A filter function accepting one argument can be specified. It will be
        called for each file and folder. It can return one of True, False,
        SKIP, YIELD, or RECURSE, with the behavior of each outlined in the
        following table::
            
                                  Don't yield   Do yield
                                +-------------+----------+
            Don't recurse into  | SKIP        | YIELD    |
                                +-------------+----------+
            Do recurse into     | RECURSE     | True     |
                                +-------------+----------+
            
            False behaves the same as RECURSE if recurse_skipped is True, or
            SKIP otherwise.
        
        If include_self is True (the default), this file (a.k.a. self) will be
        yielded as well (if it matches the specified filter function). If it's
        False, only this file's children (and their children, and so on) will
        be yielded.
        """
        include = True if filter is None else filter(self)
        if include in (YIELD, True) and include_self:
            yield self
        if include in (RECURSE, True) or (recurse_skipped and not include):
            for child in self.children or []:
                for f in child.recurse(filter, True, recurse_skipped):
                    yield f

    def change_to(self):
        """
        Sets the current working directory to self.
        
        Since File instances internally store paths in absolute form, other
        File instances will continue to work just fine after this is called.
        
        If you need to restore the working directory at any point, you might
        want to consider using :obj:`self.as_working <as_working>` instead.
        """
        raise NotImplementedError
    
    def cd(self):
        """
        An alias for :obj:`self.change_to() <change_to>`.
        """
        self.change_to()
    
    @property
    def as_working(self):
        """
        A property that returns a context manager. This context manager sets
        the working directory to self upon being entered and restores it to
        what it previously was upon being exited. One can use this to replace
        something like::
        
            old_dir = File()
            new_dir.cd()
            try:
                ...stuff...
            finally:
                old_dir.cd()
        
        with the much nicer::
        
            with new_dir.as_working:
                ...stuff...
        
        and get exactly the same effect.
        
        The context manager's __enter__ returns self (this file), so you can
        also use an "as" clause on the with statement to get access to the
        file in case you haven't got it stored in a variable anywhere.
        """
        return _AsWorking(self)

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
        raise NotImplementedError
    
    def delete(self, ignore_missing=False):
        """
        Deletes this file or folder, recursively deleting children if
        necessary.
        
        The contents parameter has no effect, and is present for backward
        compatibility.
        
        If the file does not exist and ignore_missing is False, an exception
        will be thrown. If the file does not exist but ignore_missing is True,
        this function simply does nothing.
        
        Note that symbolic links are never recursed into, and are instead
        themselves removed.
        """
        raise NotImplementedError
    
    def link_to(self, target):
        """
        Creates this file as a symbolic link pointing to other, which can be
        a pathname or an object of the same type as self. Note that if it's a
        pathname, a symbolic link will be created with the exact path
        specified; it will therefore be absolute if the path is absolute or
        relative (to the link itself) if the path is relative. If an object of
        the same type as self, however, is used, the symbolic link will always
        be absolute.
        """
        raise NotImplementedError
    
    def open_for_writing(self, append=False):
        """
        Open this file for reading in binary mode and return a Python file-like
        object from which this file's contents can be read.
        
        If append is False, the file's contents will be erased and the returned
        stream positioned at the beginning of the (now empty) file. If append
        is True, the file's contents will not be erased, and the returned
        stream will be positioned at the end of the file.
        
        Note that some implementations (e.g. SMBFile and FTPFile) don't have
        native support for writing files remotely; support in such
        implementations can be emulated by returning a wrapper around a
        temporary file that, when closed, uploads itself to the location of
        the file to be written. As a result, objects returned from
        open_for_writing should be closed before calling open_for_reading on
        the same file.
        """
        raise NotImplementedError

    def append(self, data):
        """
        Append the specified data to the end of this file.
        """
        with self.open_for_writing(append=True) as f:
            f.write(data)

    def mkdir(self, silent=False):
        """
        An alias for self.create_folder(ignore_existing=silent).
        """
        self.create_folder(ignore_existing=silent)
    
    def mkdirs(self, silent=False):
        """
        An alias for self.create_folder(ignore_existing=silent, recursive=True).
        """
        self.create_folder(ignore_existing=silent, recursive=True)
    
    makedirs = mkdirs
    
    def mkdtemp(self):
        # TODO: Write up a more proper implementation that allows a function or
        # generator of some sort to be used to generate names instead, and see
        # if it can be written in such a way as to be used with copy_to to
        # allow conflicting files to be renamed on request.
        names = tempfile._get_candidate_names()
        for _ in range(20):
            name = "tmp" + next(names) + next(names)
            f = self.child(name)
            try:
                # TODO: Create this by default with permissions such that only
                # we have access to it, like tempfile.mkdtemp does
                f.mkdir()
                return f
            except exceptions.FileExistsError:
                continue
            except IOError:
                # Really ugly hack: SFTP v3 (and hence Paramiko) doesn't have
                # any support for indicating that a mkdir failed because the
                # directory in question already exists, so we assume that any
                # failure is because the directory already exists. There's not
                # much wrong with this approach other than taking an inordinate
                # amount of time to fail when the real issue is, say, related
                # to permissions, and annoyingly breaking encapsulation in
                # quite a glaring manner.
                from fileutils.ssh import SSHFile
                if isinstance(self, SSHFile):
                    continue
                else:
                    raise

    def write(self, data, binary=True):
        """
        Overwrite this file with the specified data. After this is called,
        self.size will be equal to len(data), and self.read() will be equal to
        data. If you want to append data instead, use self.append().
        
        If binary is True (the default), the file will be written
        byte-for-byte. If it's False, the file will be written in text mode. 
        """
        with open(self.path, "wb") as f:
            f.write(data)
    
    def rename_to(self, other):
        """
        Rename this file or folder to the specified name, which should be
        another file object (but need not be of the same type as self).
        
        The default implementation simply does::
        
            self.copy_to(other)
            self.delete()
        
        (which, as a note, doesn't work for directories yet, so at present
        directories can't be renamed across different subclasses). Subclasses
        are free to provide a more specialized implementation for renames to
        files of the same type; File and SSHFile, for example, make use of
        native functions to speed up such renames (and to allow them to work
        with directories at present).
        """
        self.copy_to(other)
        self.delete()
    
    @property
    def attributes(self):
        """
        This is the new attributes system. It's highly experimental, so beware
        that it might not work as expected and that its API could change
        without notice. More to come.
        """
        return {}
    
    def copy_attributes_to(self, other, which_attributes={}):
        """
        Copy file/directory attributes from self to other.
        
        which_attributes is a dictionary indicating which attribute sets are
        to be copied. The keys are subclasses of AttributeSet (these are class
        objects themselves, not instances of said classes) and the values
        indicate whether, and how, attribute sets are to be copied:
        
            True indicates that the attribute set in question should be copied.
            The copying will be performed with the attribute set's copy_to
            method.
            
            False indicates that the attribute set in question should not be
            copied.
            
            A two-argument function can be used to copy attributes in a custom
            manner. The function will be called with the source attribute set
            as the first argument and the target attribute set as the second
            argument.
        
        One additional key, None, can be specified. Its value indicates
        whether, and how, all attribute sets not explicitly specified in the
        dictionary are to be copied. If not specified, each attribute set's
        copy_by_default property is used to decide whether or not to copy that
        attribute set.
        
        To copy POSIX permissions and mode bits only, and nothing else, one
        could use::
        
            foo.copy_attributes_to(bar, {PosixPermissions: True, None: False})
        
        To skip copying of POSIX permissions and mode bits but copy everything
        else, one could use::
        
            foo.copy_attributes_to(bar, {PosixPermissions: False})
        
        To copy only the extended attribute "user.foo", one could use::
        
            def copy_user_foo(source, target):
                target.set("user.foo", source.get("user.foo"))
            foo.copy_attributes_to(bar, {ExtendedAttributes: copy_user_foo,
                                         None: False})
        
        (This example would be easier written as::
        
            bar.attributes[ExtendedAttributes].set("user.foo,
                foo.attributes[ExtendedAttributes].get("user.foo"))
        
        so take it as purely an example.)
        """
        default_spec = which_attributes.get(None)
        for attribute_set in self.attributes.keys():
            if attribute_set in other.attributes:
                ours = self.attributes[attribute_set]
                theirs = other.attributes[attribute_set]
                # Try an attribute set specific spec first
                try:
                    spec = which_attributes[attribute_set]
                except KeyError:
                    # Wasn't specified for this particular attribute set, so
                    # use the default if one was specified
                    if default_spec is not None:
                        spec = default_spec
                    else:
                        # Default wasn't specified, so use the attribute set's
                        # default copying policy. TODO: Consider changing this
                        # to only copy if both ours.copy_by_default and
                        # theirs.copy_by_default are True; this would allow
                        # certain targets to specifically request that they not
                        # be copied to by default.
                        spec = ours.copy_by_default
                if spec is True:
                    ours.copy_to(theirs)
                elif spec is False:
                    pass
                else:
                    spec(ours, theirs)


class _AsWorking(object):
    """
    The class of the context managers returned from
    WorkingDirectory.as_working. See that method's docstring for more
    information on what this class does.
    """
    def __init__(self, folder):
        self.folder = folder
    
    def __enter__(self):
        self.old = type(self.folder)()
        self.folder.cd()
        return self.folder
    
    def __exit__(self, *args):
        self.old.cd()


















