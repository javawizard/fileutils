# This will almost certainly be broken up into multiple modules once this is
# actually done.

from abc import ABCMeta, abstractmethod, abstractproperty
import os
import hashlib
from functools import partial as _partial
import urlparse

try:
    import requests
except ImportError:
    requests = None


class Hierarchy(object):
    __metaclass__ = ABCMeta
    
    @abstractmethod
    def child(self, *names):
        pass
    
    @abstractproperty
    def parent(self):
        pass
    
    @abstractmethod
    def get_path_components(self, relative_to=None):
        pass
    
    def same_as(self, other):
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
    
    def sibling(self, *names):
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
        is equivalent to File(other).ancestor_of(self, including_self).
        """
        for ancestor in self.get_ancestors(including_self):
            if other.same_as(ancestor):
                return True
        return False

    def ancestor_of(self, other, including_self=False):
        """
        Returns true if this file is an ancestor of the specified file. A file
        is an ancestor of another file if that other file's parent is this
        file, or its parent's parent is this file, and so on.
        
        If including_self is True, the file is considered to be an ancestor of
        itself, i.e. True will be returned in the case that self == other.
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
            separator = os.path.sep
        return separator.join(self.get_path_components(relative_to))

    @property
    def path(self):
        """
        The absolute path to the file represented by this File object, in a
        format native to the operating system in use. This pathname can then be
        used with Python's traditional file-related utilities.
        
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


class Readable(object):
    __metaclass__ = ABCMeta
    
    @abstractproperty
    def exists(self):
        pass
    
    @abstractproperty
    def is_broken(self):
        pass
    
    @abstractproperty
    def is_file(self):
        pass
    
    @abstractproperty
    def is_folder(self):
        pass
    
    @abstractproperty
    def link_target(self):
        pass
    
    @abstractmethod
    def open_for_reading(self):
        # Should open in "rb" mode
        pass
    
    @property
    def is_directory(self):
        return self.is_folder
    
    @property
    def is_link(self):
        return self.link_target is not None
    
    @property
    def valid(self):
        return self.exists and (not self.is_link or not self.is_broken)

    def check_folder(self):
        """
        Checks to see whether this File refers to a folder. If it doesn't, an
        exception will be thrown.
        """
        if not self.is_folder:
            raise Exception('"%s" does not exist or is not a directory' % self._path)
    
    def check_file(self):
        """
        Checks to see whether this File refers to a file. If it doesn't, an
        exception will be thrown.
        """
        if not self.is_file:
            raise Exception('"%s" does not exist or is not a file' % self._path)
    
    def copy_to(self, other, overwrite=False):
        """
        Copies the contents of this file to the specified File object or
        pathname. An exception will be thrown if the specified file already
        exists and overwrite is False.
        
        This `does not currently work for folders
        <https://github.com/javawizard/fileutils/issues/1>`_;
        I hope to add this ability in the near future.
        """
        # If self.is_folder is True, requires isinstance(self, Listable) and
        # isinstance(other, Hierarchy) when we implement support for folders.
        # Requires isinstance(other, Writable) always.
        self.check_file()
        # TODO: Use (and catch or pass on) proper exceptions here, EAFP style
        if other.exists and not overwrite:
            raise Exception("%r already exists" % other)
        with other.open_for_writing() as write_to:
            for block in self.read_blocks():
                write_to.write(block)

    def copy_into(self, other, overwrite=False):
        """
        Copies this file to an identically named file inside the specified
        folder. This is just shorthand for self.copy_to(other.child(self.name))
        which, from experience, seems to be by far the most common use case for
        the copy_to function.
        """
        self.copy_to(other.child(self.name), overwrite)

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
        with self.open_for_reading() as f:
            # TODO: Use read_blocks instead; read_blocks didn't exist when this
            # was written in the original fileutils, but it does now, so use it
            for block in iter(_partial(f.read, 10), ""):
                hasher.update(block)
        if return_hex:
            hasher = hasher.hexdigest()
        return hasher
    
    def read_blocks(self, block_size=16384):
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


class Listable(Readable):
    __metaclass__ = ABCMeta
    
    @abstractproperty
    def children(self):
        pass
    
    @abstractproperty
    def child_names(self):
        pass


class ChildrenMixin(Listable, Readable):
    @property
    def children(self):
        """
        A list of all of the children of this file, as a list of File objects.
        If this file is not a folder, the value of this property is None.
        """
        if not self.is_folder:
            return
        return [self.child(p) for p in self.child_names]


class Sizable(object):
    __metaclass__ = ABCMeta
    
    @abstractproperty
    def size(self):
        pass


class WorkingDirectory(object):
    __metaclass__ = ABCMeta
    
    @abstractmethod
    def change_to(self):
        pass
    
    def cd(self):
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


class Writable(object):
    __metaclass__ = ABCMeta
    
    @abstractmethod
    def create_folder(self, ignore_existing=False, recursive=False):
        pass
    
    @abstractmethod
    def delete(self, ignore_missing=False):
        pass
    
    @abstractmethod
    def link_to(self, target):
        pass
    
    @abstractmethod
    def open_for_writing(self, append=False):
        pass

#    def append(self, data):
#        """
#        Append the specified data to the end of this file.
#        """
#        with open(self.path, "ab") as f:
#            f.write(data)

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


class File(Hierarchy, ChildrenMixin, Listable, Readable, Sizable,
           WorkingDirectory, Writable):
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
        path = os.path.abspath(path)
        self._path = path
    
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

    def get_path_components(self, relative_to=None):
        if relative_to is None:
            return self._path.split(os.path.sep)
        else:
            return os.path.relpath(self._path, File(relative_to)._path).split(os.sep)

    @property
    def child_names(self):
        if not self.is_folder:
            return
        return sorted(os.listdir(self._path))

    @property
    def is_folder(self):
        """
        True if this File is a folder, False if it isn't. If the file/folder
        doesn't actually exist yet, this will be False.
        
        If this file is a symbolic link that points to a folder, this will be
        True.
        """
        return os.path.isdir(self._path)

    @property
    def is_file(self):
        """
        True if this File is a file, False if it isn't. If the file/folder
        doesn't actually exist yet, this will be False.
        
        If this file is a symbolic link that points to a file, this will be
        True.
        """
        return os.path.isfile(self._path)

    @property
    def exists(self):
        """
        True if this file/folder exists, False if it doesn't. This will be True
        even for broken symbolic links; use self.valid if you want an
        alternative that returns False for broken symbolic links.
        """
        return os.path.lexists(self._path)

    @property
    def is_link(self):
        """
        True if this File is a symbolic link, False if it isn't. This will be
        True even for broken symbolic links.
        """
        return os.path.islink(self._path)

    @property
    def is_broken(self):
        """
        True if this File is a symbolic link that is broken, False if it isn't.
        """
        return self.is_link and not os.path.exists(self._path)

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
        return open(self.path, "rb")

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
                raise Exception("The folder %r already exists." % self.path)
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
        if not self.exists:
            if not ignore_missing:
                raise Exception("This file does not exist.")
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
            return open(self.path, "ab")
        else:
            return open(self.path, "wb")

    def __str__(self):
        return "fileutils2.File(%r)" % self._path
    
    __repr__ = __str__
    
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


if requests is not None:
    class URL(Readable, Hierarchy):
        # NOTE: We don't yet handle query parameters and fragments properly;
        # some things (like self.parent) preserve them, while others (like
        # self.child) do away with them. Figure out what's the sane thing to
        # do and do it.
        
        exists = True
        is_broken = False
        is_file = True
        is_folder = False
        link_target = None
        
        def __init__(self, url):
            self._url = urlparse.urlparse(url)
            # Normalize out trailing slashes in the path when comparing URLs.
            # TODO: We treat http://foo/a and http://foo/a/ as identical both
            # here and in self.parent, self.child, and so forth; decide if this
            # is really the right thing to do.
            self._normal_url = self._url._replace(path=self._url.path.rstrip("/"))
        
        def open_for_reading(self):
            response = requests.get(self._url, stream=True)
            response.raise_for_status()
            response.raw.decode_content=True
            # TODO: Add hooks here to check the content-length response header
            # and raise an exception if we hit EOF before reading that many
            # bytes
            return response.raw
        
        def child(self, *names):
            if not names:
                return self
            path = self._url.path
            if not path.endswith("/"):
                path = path + "/"
            new_url = urlparse.urljoin(self._url._replace(path=path).geturl(), names[0])
            return URL(new_url).child(*names[1:])
        
        @property
        def parent(self, *names):
            path = self._url.path.rstrip("/")
            if not path: # Nothing left, so we must be at the root
                return None
            base, _, _ = path.rpartition("/")
            return URL(self._url._replace(path=base).geturl())
        
        def get_path_components(self, relative_to=None):
            if relative_to:
                raise Exception("URLs don't yet support "
                                "get_path_components(relative_to=...)")
            # The list comprehension filters out empty names which are
            # meaningless to nearly every web server I've used. If there ends
            # up being a practical need for preserving these somehow, I'll
            # probably expose them as another property. 
            return [c for c in self._url.geturl().split("/") if c]
        
        @property
        def url(self):
            return self._url.geturl()
            
        def __str__(self):
            return "fileutils2.URL(%r)" % self._url.geturl()
        
        __repr__ = __str__
        
        # Use __cmp__ instead of the rich comparison operators for brevity
        def __cmp__(self, other):
            if not isinstance(other, URL):
                return NotImplemented
            return cmp(self._url, other._url)
        
        def __hash__(self):
            return hash(self._url)
        
        def __nonzero__(self):
            return True
        
        def same_as(self, other):
            return (Hierarchy.same_as(self, other) and
                    self._url._replace(path="") == other._url._replace(path=""))
        


































