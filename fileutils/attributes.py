
import stat

class AttributeSet(object):
    def copy_to(self, other):
        raise NotImplementedError


class PosixPermissions(AttributeSet):
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
    
    # Note to self: add execute here that returns... probably True if any user
    # can execute, and setting it sets execute for... probably all users who
    # can read. That way, the executable bit but nothing else can be copied
    # from one file's permissions to anohter with a.execute = b.execute.
    # (And so note that setting execute to false would clear all three execute
    # bits.)



class ExtendedAttributes(AttributeSet):
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
                # Just ignore for now. Might want to consider raising some sort
                # of warning later.
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
