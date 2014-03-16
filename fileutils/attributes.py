
import stat

class AttributeSet(object):
    """
    A set of attributes on a file.
    
    Each of the subclasses of this class provide an interface to a particular
    set of filesystem attributes. PosixPermissions, for example, provides an
    interface to POSIX-style permissions and mode bits, and ExtendedAttributes
    provides a platform-neutral interface to user-defined extended attributes.
    
    AttributeSet instances can be obtained from any BaseFile instance's
    attributes property. This property is a dictionary whose keys are the
    various subclasses of AttributeSet (the class objects themselves, not
    instances of said classes) and whose values are instances of the
    corresponding subclass. For example, one could, on a POSIX system, get an
    instance of PosixPermissions corresponding to /home with::
    
        File('/home').attributes[PosixPermissions]
    
    Instances of these subclasses can then be used to read and modify the
    file's attributes in a subclass specific manner. PosixPermissions has
    properties that can be used to set the various mode bits, so, for example,
    one could grant a particular file's group permission to write to that file
    thus::
    
        some_file.attributes[PosixPermissions].group.write = True
    """
    def copy_to(self, other):
        """
        Copy attributes exposed by this attribute set to the specified
        attribute set.
        
        All of the subclasses of AttributeSet provide implementations of this
        method. Subclasses of those subclasses shouldn't need to override this.
        """
        raise NotImplementedError
    
    @property
    def copy_by_default(self):
        """
        True if this attribute set should be copied by default, false if it
        shouldn't be.
        
        Functions like BaseFile.copy_attributes_to (and, by extension,
        BaseFile.copy_to and BaseFile.copy_into) consult this property when
        they're not given further direction as to which attribute sets should
        be copied from one file to another.
        """
        raise NotImplementedError


class PosixPermissions(AttributeSet):
    """
    An attribute set providing access to a file's POSIX permission and mode
    bits.
    """
    copy_by_default = True
    
    @property
    def mode(self):
        raise NotImplementedError
    
    def set(self, mask, value):
        # Takes one of the stat.S_* constants
        mode = self.mode
        mode &= ~mask
        if value:
            mode |= mask
        self.mode = mode
    
    def get(self, mask):
        return bool(self.mode & mask)
    
    @property
    def user(self):
        return _ModeAccessor(self, stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR)
    
    @property
    def group(self):
        return _ModeAccessor(self, stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP)
    
    @property
    def other(self):
        return _ModeAccessor(self, stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH)
    
    @property
    def setuid(self):
        return self.get(stat.S_ISUID)
    
    @setuid.setter
    def setuid(self, value):
        self.set(stat.S_ISUID, value)
    
    @property
    def setgid(self):
        return self.get(stat.S_ISGID)
    
    @setgid.setter
    def setgid(self, value):
        self.set(stat.S_ISGID, value)
    
    @property
    def sticky(self):
        return self.get(stat.S_ISVTX)
    
    @sticky.setter
    def sticky(self, value):
        self.set(stat.S_ISVTX, value)
    
    @property
    def execute(self):
        """
        True if any of the file's execute bits are set, false if none of them
        are.
        
        Setting the value of this property to True turns on the corresponding
        execute bit for each read bit that's set (but does not clear other
        execute bits that are already set). Setting the value of this property
        to False clears all executable bits that are set.
        """
        return bool(self.mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    
    @execute.setter
    def execute(self, value):
        mode = self.mode
        if value:
            # Set executable bits where the corresponding read bit is set
            if mode & stat.S_IRUSR:
                mode |= stat.S_IXUSR
            if mode & stat.S_IRGRP:
                mode |= stat.S_IXGRP
            if mode & stat.S_IROTH:
                mode |= stat.S_IXOTH
        else:
            # Clear all executable bits
            mode &= ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.mode = mode
    
    # Note to self: add execute here that returns... probably True if any user
    # can execute, and setting it sets execute for... probably all users who
    # can read. That way, the executable bit but nothing else can be copied
    # from one file's permissions to anohter with a.execute = b.execute.
    # (And so note that setting execute to false would clear all three execute
    # bits.)



class ExtendedAttributes(AttributeSet):
    copy_by_default = True
    
    def get(self, name):
        raise NotImplementedError
    
    def set(self, name, value):
        raise NotImplementedError
    
    def list(self):
        raise NotImplementedError
    
    def delete(self, name):
        raise NotImplementedError
    
    def copy_to(self, other):
        # Delete existing attributes
        for name in other.list():
            other.delete(name)
        # Then copy over our attributes
        for name in self.list():
            try:
                other.set(name, self.get(name))
            except EnvironmentError:
                # Probably because the target file is on a filesystem that
                # places restrictions on the names of extended attributes; just
                # ignore for now. Might want to consider raising some sort of
                # warning later.
                pass


class _ModeAccessor(object):
    def __init__(self, attributes, r, w, x):
        self._attributes = attributes
        self._r = r
        self._w = w
        self._x = x
    
    @property
    def read(self):
        return self._attributes.get(self._r)
    
    @read.setter
    def read(self, value):
        self._attributes.set(self._r, value)
    
    @property
    def write(self):
        return self._attributes.get(self._w)
    
    @write.setter
    def write(self, value):
        self._attributes.set(self._w, value)
    
    @property
    def execute(self):
        return self._attributes.get(self._x)
    
    @execute.setter
    def execute(self, value):
        self._attributes.set(self._x, value)
    
    def __repr__(self):
        mode = self._attributes.mode
        r = "r" if mode & self._r else "-"
        w = "w" if mode & self._w else "-"
        x = "x" if mode & self._x else "-"
        return "<mode " + r + w + x + ">"
    
    __str__ = __repr__
