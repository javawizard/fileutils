
class AttributeSet(object):
    def copy_to(self, target_attributes):
        raise NotImplementedError


class PosixPermissions(AttributeSet):
    pass


class ExtendedAttributes(AttributeSet):
    def get(self, name):
        raise NotImplementedError
    
    def set(self, name, value):
        raise NotImplementedError
    
    def list(self):
        raise NotImplementedError
    
    def delete(self, name):
        raise NotImplementedError
    
    def copy_to(self, target_attributes):
        # Delete existing attributes
        for name in target_attributes.list():
            target_attributes.delete(name)
        # Then copy over our attributes
        for name in self.list():
            target_attributes.set(name, self.get(name))
