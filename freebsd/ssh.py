from base64 import decodestring
from struct import unpack
import binascii


class InvalidKeyType(Exception):
    pass


class InvalidKey(Exception):
    pass


class PubKey(object):

    key_types = ('ssh-rsa', 'ssh-dsa', 'ssh-ecdsa')

    # http://stackoverflow.com/questions/2494450/ssh-rsa-public-key-
    # validation-using-a-regular-expression
    @classmethod
    def validate_key(cls, key_type, key):
        try:
            data = decodestring(key)
        except binascii.Error:
            raise InvalidKey()
        int_len = 4
        str_len = unpack('>I', data[:int_len])[0]
        if data[int_len:int_len + str_len] != key_type:
            raise InvalidKey()

    def __init__(self, key_type, key, comment):
        if key_type not in self.key_types:
            raise InvalidKeyType()
        self.key_type = key_type

        PubKey.validate_key(key_type, key)
        self.key = key

        self.comment = unicode(comment)

    def __hash__(self):
        return hash(frozenset(self.__dict__.items()))

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    @classmethod
    def from_str(cls, line):
        key_type, key, comment = line.split()
        return PubKey(key_type, key, comment)

    def __unicode__(self):
        return u' '.join((self.key_type, self.key, self.comment))

    def __repr__(self):
        return u'<PubKey: %s>' % unicode(self)


import unittest


class SshTestCase(unittest.TestCase):
    def setUp(self):
        self.p1 = PubKey.from_str('ssh-rsa AAAAB3NzaC1yc2EA comment')
        self.p2 = PubKey.from_str('ssh-rsa AAAAB3NzaC1yc2EA comment')
        self.p3 = PubKey.from_str('ssh-rsa AAAAB3NzaC1yc2EC comment')

    def test_invalid_key_type(self):
        self.assertRaises(InvalidKeyType, PubKey, 'ssh-inv', 'x', 'comment')

    def test_valid_key(self):
        PubKey('ssh-rsa', 'AAAAB3NzaC1yc2EA', 'comment')

    def test_invalid_key(self):
        self.assertRaises(InvalidKey, PubKey, 'ssh-rsa', 'x', 'comment')

    def test_invalid_key2(self):
        self.assertRaises(InvalidKey, PubKey, 'ssh-rsa',
                          'AAAAB3MzaC1yc2EA', 'comment')

    def test_repr(self):
        p = PubKey('ssh-rsa', 'AAAAB3NzaC1yc2EA', 'comment')
        self.assertEqual(
            repr(p), '<PubKey: ssh-rsa AAAAB3NzaC1yc2EA comment>')

    def test_unicode(self):
        p = PubKey('ssh-rsa', 'AAAAB3NzaC1yc2EA', 'comment')
        self.assertEqual(unicode(p), 'ssh-rsa AAAAB3NzaC1yc2EA comment')

    def test_from_str(self):
        p = PubKey.from_str('ssh-rsa AAAAB3NzaC1yc2EA comment')
        self.assertEqual(unicode(p), 'ssh-rsa AAAAB3NzaC1yc2EA comment')

    def test_eq(self):
        self.assertEqual(self.p1, self.p2)
        self.assertNotEqual(self.p1, self.p3)

    def test_hash(self):
        s = set()
        s.add(self.p1)
        s.add(self.p2)
        s.add(self.p3)
        self.assertEqual(len(s), 2)

if __name__ == '__main__':
    unittest.main()
