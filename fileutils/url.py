
from fileutils.interface import Hierarchy, Readable
from fileutils.constants import FILE, LINK
import urlparse

try:
    import requests
except ImportError:
    requests = None

if requests:
    REDIRECT_CODES = (requests.codes.moved_permanently,
                      requests.codes.found,
                      requests.codes.temporary_redirect,
                      requests.codes.see_other)
    SUCCESS_CODES = (requests.codes.ok,)
    
    class URL(Readable, Hierarchy):
        """
        A concrete file implementation exposing a file-like interface to URLs.
        """
        # NOTE: We don't yet handle query parameters and fragments properly;
        # some things (like self.parent) preserve them, while others (like
        # self.child) do away with them. Figure out what's the sane thing to
        # do and do it.
        
        type = FILE
        link_target = None
        
        def __init__(self, url):
            self._url = urlparse.urlparse(url)
            # Normalize out trailing slashes in the path when comparing URLs.
            # TODO: We treat http://foo/a and http://foo/a/ as identical both
            # here and in self.parent, self.child, and so forth; decide if this
            # is really the right thing to do.
            self._normal_url = self._url._replace(path=self._url.path.rstrip("/"))
        
        @property
        def type(self):
            response = requests.head(self._url.geturl(), allow_redirects=False)
            if response.status_code in SUCCESS_CODES:
                return FILE
            elif response.status_code in REDIRECT_CODES:
                return LINK
            else:
                return None
        
        @property
        def link_target(self):
            response = requests.head(self._url.geturl(), allow_redirects=False)
            if response.status_code in REDIRECT_CODES:
                return response.headers["Location"]
            else:
                return None
        
        @property
        def size(self):
            # TODO: We can save an extra request by just making the request
            # against our original URL and handling 30* redirects manually
            # (perhaps recursively call URL(response.headers["location"]).size)
            response = requests.head(self.dereference(recursive=True)._url.geturl())
            if response.status_code in SUCCESS_CODES:
                try:
                    return int(response.headers["content-length"])
                except KeyError: # Fallback
                    size = 0
                    for block in self.read_blocks():
                        size += len(block)
                    return size
            else:
                return 0

        def dereference(self, recursive=False):
            link_target = self.link_target
            if link_target is None: # We're not a redirect
                return self
            target = (self.parent or self).child(link_target)
            if recursive:
                return target.dereference(recursive=True)
            else:
                return target
            
        def open_for_reading(self):
            response = requests.get(self._url.geturl(), stream=True, allow_redirects=True)
            if response.status_code not in SUCCESS_CODES:
                raise IOError("URL returned HTTP status code {0}".format(response.status_code))
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
            return [""] + [c for c in self._url.path.split("/") if c]
        
        @property
        def url(self):
            return self._url.geturl()
            
        def __str__(self):
            return "fileutils.URL(%r)" % self._url.geturl()
        
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
