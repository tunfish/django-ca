# This file is part of django-ca (https://github.com/mathiasertl/django-ca).
#
# django-ca is free software: you can redistribute it and/or modify it under the terms of the GNU
# General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# django-ca is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with django-ca.  If not,
# see <http://www.gnu.org/licenses/>

"""Test the sign_cert management command."""

import os
import stat
import unittest
from datetime import datetime
from datetime import timedelta
from io import StringIO

from cryptography.hazmat.primitives.serialization import Encoding

from django.conf import settings
from django.core.files.storage import FileSystemStorage

from freezegun import freeze_time

from .. import ca_settings
from ..extensions import ExtendedKeyUsage
from ..extensions import IssuerAlternativeName
from ..extensions import KeyUsage
from ..extensions import SubjectAlternativeName
from ..extensions import TLSFeature
from ..models import Certificate
from ..models import CertificateAuthority
from ..signals import post_issue_cert
from ..signals import pre_issue_cert
from ..subject import Subject
from ..utils import ca_storage
from .base import DjangoCAWithGeneratedCAsTestCase
from .base import certs
from .base import override_settings
from .base import override_tmpcadir
from .base import timestamps


@override_settings(CA_MIN_KEY_SIZE=1024, CA_PROFILES={}, CA_DEFAULT_SUBJECT={})
@freeze_time(timestamps['everything_valid'])
class SignCertTestCase(DjangoCAWithGeneratedCAsTestCase):
    """Main test class for this command."""

    def setUp(self):
        super().setUp()
        self.ca = self.cas['root']
        self.csr_pem = certs['root-cert']['csr']['pem']

    @override_tmpcadir()
    def test_from_stdin(self):
        """Test reading CSR from stdin."""
        stdin = StringIO(self.csr_pem)
        subject = Subject([('CN', 'example.com')])
        with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            stdout, stderr = self.cmd('sign_cert', ca=self.ca, subject=subject, stdin=stdin)
        self.assertEqual(stderr, '')
        self.assertEqual(pre.call_count, 1)

        cert = Certificate.objects.first()
        self.assertPostIssueCert(post, cert)
        self.assertSignature([self.ca], cert)
        self.assertSubject(cert.x509, subject)
        self.assertEqual(stdout, 'Please paste the CSR:\n%s' % cert.pub)

        self.assertEqual(cert.key_usage, KeyUsage({
            'critical': True, 'value': ['digitalSignature', 'keyAgreement', 'keyEncipherment']}))
        self.assertEqual(cert.extended_key_usage, ExtendedKeyUsage({'value': ['serverAuth']}))
        self.assertEqual(cert.subject_alternative_name,
                         SubjectAlternativeName({'value': ['DNS:example.com']}))
        self.assertIssuer(self.ca, cert)
        self.assertAuthorityKeyIdentifier(self.ca, cert)

    @override_tmpcadir()
    def test_usable_cas(self):
        """Test signing with all usable CAs."""

        for name, ca in self.usable_cas.items():
            cname = '%s-signed.example.com' % name
            stdin = StringIO(self.csr_pem)
            subject = Subject([('CN', cname)])

            with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
                stdout, stderr = self.cmd('sign_cert', ca=ca, subject=subject,
                                          password=certs[name]['password'], stdin=stdin)

            self.assertEqual(stderr, '')
            self.assertEqual(pre.call_count, 1)

            cert = Certificate.objects.get(ca=ca, cn=cname)
            self.assertPostIssueCert(post, cert)
            self.assertSignature(reversed(ca.bundle), cert)
            self.assertSubject(cert.x509, subject)
            self.assertEqual(stdout, 'Please paste the CSR:\n%s' % cert.pub)

            self.assertEqual(cert.key_usage,
                             KeyUsage({'critical': True,
                                       'value': ['digitalSignature', 'keyAgreement', 'keyEncipherment']}))
            self.assertEqual(cert.extended_key_usage, ExtendedKeyUsage({'value': ['serverAuth']}))
            self.assertEqual(cert.subject_alternative_name,
                             SubjectAlternativeName({'value': ['DNS:%s' % cname]}))
            self.assertIssuer(ca, cert)
            self.assertAuthorityKeyIdentifier(ca, cert)

    @override_tmpcadir()
    def test_from_file(self):
        """Test reading CSR from file."""
        csr_path = os.path.join(ca_settings.CA_DIR, 'test.csr')
        with open(csr_path, 'w') as csr_stream:
            csr_stream.write(self.csr_pem)

        try:
            subject = Subject([('CN', 'example.com'), ('emailAddress', 'user@example.com')])
            with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
                stdout, stderr = self.cmd('sign_cert', ca=self.ca, subject=subject, csr=csr_path)
            self.assertEqual(stderr, '')
            self.assertEqual(pre.call_count, 1)

            cert = Certificate.objects.first()
            self.assertPostIssueCert(post, cert)
            self.assertSignature([self.ca], cert)

            self.assertSubject(cert.x509, subject)
            self.assertEqual(stdout, cert.pub)
            self.assertEqual(cert.key_usage,
                             KeyUsage({'critical': True,
                                       'value': ['digitalSignature', 'keyAgreement', 'keyEncipherment']}))
            self.assertEqual(cert.extended_key_usage, ExtendedKeyUsage({'value': ['serverAuth']}))
            self.assertEqual(cert.subject_alternative_name,
                             SubjectAlternativeName({'value': ['DNS:example.com']}))
        finally:
            os.remove(csr_path)

    @override_tmpcadir()
    def test_to_file(self):
        """Test writing PEM to file."""
        out_path = os.path.join(ca_settings.CA_DIR, 'test.pem')
        stdin = StringIO(self.csr_pem)

        try:
            with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
                stdout, stderr = self.cmd('sign_cert', ca=self.ca, subject=Subject([('CN', 'example.com')]),
                                          out=out_path, stdin=stdin)
            self.assertEqual(pre.call_count, 1)

            cert = Certificate.objects.first()
            self.assertPostIssueCert(post, cert)
            self.assertSignature([self.ca], cert)
            self.assertEqual(stdout, 'Please paste the CSR:\n')
            self.assertEqual(stderr, '')

            self.assertIssuer(self.ca, cert)
            self.assertAuthorityKeyIdentifier(self.ca, cert)

            with open(out_path) as out_stream:
                from_file = out_stream.read()

            self.assertEqual(cert.pub, from_file)
        finally:
            if os.path.exists(out_path):
                os.remove(out_path)

    @override_tmpcadir()
    def test_no_dns_cn(self):
        """Test using a CN that is not a vlaid DNS name."""
        # Use a CommonName that is *not* a valid DNSName. By default, this is added as a subjectAltName, which
        # should fail.

        stdin = StringIO(self.csr_pem)
        cname = 'foo bar'
        msg = r'^%s: Could not parse CommonName as subjectAlternativeName\.$' % cname

        with self.assertCommandError(msg), self.assertSignal(pre_issue_cert) as pre, \
                self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=self.ca, subject=Subject([('CN', cname)]), cn_in_san=True, stdin=stdin)
        self.assertFalse(pre.called)
        self.assertFalse(post.called)

    @override_tmpcadir()
    def test_cn_not_in_san(self):
        """Test adding a CN that is not in the SAN."""
        stdin = StringIO(self.csr_pem)
        with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            stdout, stderr = self.cmd('sign_cert', ca=self.ca, subject=Subject([('CN', 'example.net')]),
                                      cn_in_san=False, alt=SubjectAlternativeName({'value': ['example.com']}),
                                      stdin=stdin)
        self.assertEqual(pre.call_count, 1)

        cert = Certificate.objects.first()
        self.assertPostIssueCert(post, cert)
        self.assertSignature([self.ca], cert)
        self.assertIssuer(self.ca, cert)
        self.assertAuthorityKeyIdentifier(self.ca, cert)
        self.assertSubject(cert.x509, [('CN', 'example.net')])
        self.assertEqual(stdout, 'Please paste the CSR:\n%s' % cert.pub)
        self.assertEqual(stderr, '')
        self.assertEqual(cert.subject_alternative_name,
                         SubjectAlternativeName({'value': ['DNS:example.com']}))

    @override_tmpcadir()
    def test_no_san(self):
        """Test signing without passing any SANs."""
        stdin = StringIO(self.csr_pem)
        subject = Subject([('CN', 'example.net')])
        with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            stdout, stderr = self.cmd('sign_cert', ca=self.ca, subject=subject, cn_in_san=False,
                                      alt=SubjectAlternativeName(), stdin=stdin)
        self.assertEqual(pre.call_count, 1)

        cert = Certificate.objects.first()
        self.assertPostIssueCert(post, cert)
        self.assertSignature([self.ca], cert)
        self.assertSubject(cert.x509, subject)
        self.assertIssuer(self.ca, cert)
        self.assertAuthorityKeyIdentifier(self.ca, cert)
        self.assertEqual(stdout, 'Please paste the CSR:\n%s' % cert.pub)
        self.assertEqual(stderr, '')
        self.assertIsNone(cert.subject_alternative_name)

    @override_tmpcadir(CA_DEFAULT_SUBJECT=[
        ('C', 'AT'),
        ('ST', 'Vienna'),
        ('L', 'Vienna'),
        ('O', 'MyOrg'),
        ('OU', 'MyOrgUnit'),
        ('CN', 'CommonName'),
        ('emailAddress', 'user@example.com'),
    ])
    def test_profile_subject(self):
        """Test signing with a subject in the profile."""
        self.assertEqual(next(t[1] for t in ca_settings.CA_DEFAULT_SUBJECT if t[0] == 'O'), 'MyOrg')
        self.assertEqual(next(t[1] for t in ca_settings.CA_DEFAULT_SUBJECT if t[0] == 'OU'), 'MyOrgUnit')

        # first, we only pass an subjectAltName, meaning that even the CommonName is used.
        stdin = StringIO(self.csr_pem)
        with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            stdout, stderr = self.cmd('sign_cert', ca=self.ca, cn_in_san=False,
                                      alt=SubjectAlternativeName({'value': ['example.net']}), stdin=stdin)
        self.assertEqual(stderr, '')
        self.assertEqual(pre.call_count, 1)

        cert = Certificate.objects.first()
        self.assertPostIssueCert(post, cert)
        self.assertSignature([self.ca], cert)
        self.assertSubject(cert.x509, ca_settings.CA_DEFAULT_SUBJECT)
        self.assertIssuer(self.ca, cert)
        self.assertAuthorityKeyIdentifier(self.ca, cert)
        self.assertEqual(stdout, 'Please paste the CSR:\n%s' % cert.pub)

        # replace subject fields via command-line argument:
        subject = Subject([
            ('C', 'US'),
            ('ST', 'California'),
            ('L', 'San Francisco'),
            ('O', 'MyOrg2'),
            ('OU', 'MyOrg2Unit2'),
            ('CN', 'CommonName2'),
            ('emailAddress', 'user@example.net'),
        ])
        stdin = StringIO(self.csr_pem)
        with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=self.ca, cn_in_san=False,
                     alt=SubjectAlternativeName({'value': ['example.net']}), stdin=stdin, subject=subject)
        self.assertEqual(pre.call_count, 1)

        cert = Certificate.objects.get(cn='CommonName2')
        self.assertPostIssueCert(post, cert)
        self.assertSubject(cert.x509, subject)

    @override_tmpcadir()
    def test_extensions(self):
        """Test setting extensions for the signed certificate."""

        self.ca.issuer_alt_name = 'DNS:ian.example.com'
        self.ca.save()

        stdin = StringIO(self.csr_pem)
        cmdline = [
            'sign_cert', '--subject=%s' % Subject([('CN', 'example.com')]),
            '--ca=%s' % self.ca.serial,
            '--key-usage=critical,keyCertSign',
            '--ext-key-usage=clientAuth',
            '--alt=URI:https://example.net',
            '--tls-feature=OCSPMustStaple',
        ]

        with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            stdout, stderr = self.cmd_e2e(cmdline, stdin=stdin)
        self.assertEqual(pre.call_count, 1)
        self.assertEqual(stderr, '')

        cert = Certificate.objects.first()
        self.assertPostIssueCert(post, cert)
        self.assertSignature([self.ca], cert)
        self.assertSubject(cert.x509, [('CN', 'example.com')])
        self.assertEqual(stdout, 'Please paste the CSR:\n%s' % cert.pub)
        self.assertEqual(cert.key_usage, KeyUsage({'critical': True, 'value': ['keyCertSign']}))
        self.assertEqual(cert.extended_key_usage, ExtendedKeyUsage({'value': ['clientAuth']}))
        self.assertEqual(cert.subject_alternative_name,
                         SubjectAlternativeName({'value': ['URI:https://example.net', 'DNS:example.com']}))
        self.assertEqual(cert.tls_feature, TLSFeature({'value': ['OCSPMustStaple']}))
        self.assertEqual(cert.issuer_alternative_name,
                         IssuerAlternativeName({'value': [self.ca.issuer_alt_name]}))

    @override_tmpcadir(CA_DEFAULT_SUBJECT={})
    def test_no_subject(self):
        """Test signing without a subject (but SANs)."""
        stdin = StringIO(self.csr_pem)
        with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            stdout, stderr = self.cmd('sign_cert', ca=self.ca,
                                      alt=SubjectAlternativeName({'value': ['example.com']}), stdin=stdin)

        cert = Certificate.objects.first()

        self.assertEqual(pre.call_count, 1)
        self.assertPostIssueCert(post, cert)
        self.assertSignature([self.ca], cert)
        self.assertSubject(cert.x509, [('CN', 'example.com')])
        self.assertEqual(stdout, 'Please paste the CSR:\n%s' % cert.pub)
        self.assertEqual(stderr, '')
        self.assertEqual(cert.subject_alternative_name,
                         SubjectAlternativeName({'value': ['DNS:example.com']}))

    @override_tmpcadir(CA_DEFAULT_SUBJECT={})
    def test_with_password(self):
        """Test signing with a CA that is protected with a password."""
        password = b'testpassword'
        ca = self.cas['pwd']
        self.assertIsNotNone(ca.key(password=password))

        ca = CertificateAuthority.objects.get(pk=ca.pk)

        # Giving no password raises a CommandError
        stdin = StringIO(self.csr_pem)
        with self.assertCommandError('^Password was not given but private key is encrypted$'), \
                self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=ca, alt=SubjectAlternativeName({'value': ['example.com']}), stdin=stdin)
        self.assertEqual(pre.call_count, 0)
        self.assertEqual(post.call_count, 0)

        # Pass a password
        stdin = StringIO(self.csr_pem)
        ca = CertificateAuthority.objects.get(pk=ca.pk)
        with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=ca, alt=SubjectAlternativeName({'value': ['example.com']}),
                     stdin=stdin, password=password)
        self.assertEqual(pre.call_count, 1)
        self.assertEqual(post.call_count, 1)

        # Pass the wrong password
        stdin = StringIO(self.csr_pem)
        ca = CertificateAuthority.objects.get(pk=ca.pk)
        with self.assertCommandError(self.re_false_password), \
                self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=ca, alt=SubjectAlternativeName({'value': ['example.com']}),
                     stdin=stdin, password=b'wrong')
        self.assertFalse(pre.called)
        self.assertFalse(post.called)

    @override_tmpcadir(CA_DEFAULT_SUBJECT={})
    @unittest.skipUnless(isinstance(ca_storage, FileSystemStorage),
                         'Test only makes sense with local filesystem storage.')
    def test_unparseable(self):
        """Test creating a cert where the CA private key contains bogus data."""
        key_path = os.path.join(ca_storage.location, self.ca.private_key_path)

        os.chmod(key_path, stat.S_IWUSR | stat.S_IRUSR)
        with open(key_path, 'w') as stream:
            stream.write('bogus')
        os.chmod(key_path, stat.S_IRUSR)

        # Giving no password raises a CommandError
        msg = r'^Could not deserialize key data\.'
        if settings.CRYPTOGRAPHY_VERSION >= (3, 3):
            # msg got changed in version 3.3
            msg += r' The data may be in an incorrect format or it may be encrypted with an unsupported algorithm\.'  # NOQA: E501
        msg += '$'

        stdin = StringIO(self.csr_pem)
        with self.assertCommandError(msg), \
                self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=self.ca, alt=['example.com'], stdin=stdin)
        self.assertEqual(pre.call_count, 0)
        self.assertEqual(post.call_count, 0)

    @override_tmpcadir()
    def test_der_csr(self):
        """Test using a DER CSR."""
        csr_path = os.path.join(ca_settings.CA_DIR, 'test.csr')
        with open(csr_path, 'wb') as csr_stream:
            csr_stream.write(certs['child-cert']['csr']['der'])

        try:
            subject = Subject([('CN', 'example.com'), ('emailAddress', 'user@example.com')])
            with self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
                stdout, stderr = self.cmd('sign_cert', ca=self.ca, subject=subject, csr=csr_path,
                                          csr_format=Encoding.DER)
            self.assertEqual(pre.call_count, 1)
            self.assertEqual(stderr, '')

            cert = Certificate.objects.first()
            self.assertPostIssueCert(post, cert)
            self.assertSignature([self.ca], cert)

            self.assertSubject(cert.x509, subject)
            self.assertEqual(stdout, cert.pub)
            self.assertEqual(cert.key_usage,
                             KeyUsage({'critical': True,
                                       'value': ['digitalSignature', 'keyAgreement', 'keyEncipherment']}))
            self.assertEqual(cert.extended_key_usage, ExtendedKeyUsage({'value': ['serverAuth']}))
            self.assertEqual(cert.subject_alternative_name,
                             SubjectAlternativeName({'value': ['DNS:example.com']}))
        finally:
            os.remove(csr_path)

    @override_tmpcadir()
    def test_expiry_too_late(self):
        """Test signing with an expiry after the CA expires."""
        time_left = (self.ca.expires - datetime.now()).days
        expires = timedelta(days=time_left + 3)
        stdin = StringIO(self.csr_pem)

        with self.assertCommandError(
                r'^Certificate would outlive CA, maximum expiry for this CA is {} days\.$'.format(time_left)
        ), self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=self.ca, alt={'value': ['example.com']}, expires=expires, stdin=stdin)
        self.assertFalse(pre.called)
        self.assertFalse(post.called)

    @override_tmpcadir()
    def test_no_cn_or_san(self):
        """Test signing a cert that has neither CN nor SAN."""
        with self.assertCommandError(
                r'^Must give at least a CN in --subject or one or more --alt arguments\.$'), \
                self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=self.ca, subject=Subject([('C', 'AT')]))
        self.assertFalse(pre.called)
        self.assertFalse(post.called)

    @override_tmpcadir()
    def test_wrong_format(self):
        """Test signing with an invalid CSR format."""
        stdin = StringIO(self.csr_pem)

        with self.assertCommandError('Unknown CSR format passed: foo$'), \
                self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=self.ca, alt=SubjectAlternativeName({'value': ['example.com']}),
                     csr_format='foo', stdin=stdin)
        self.assertFalse(pre.called)
        self.assertFalse(post.called)

    @override_tmpcadir()
    @freeze_time(timestamps['everything_valid'])
    def test_revoked_ca(self):
        """Test signing with a revoked CA."""
        self.ca.revoke()
        stdin = StringIO(self.csr_pem)
        subject = Subject([('CN', 'example.com')])

        with self.assertCommandError(
                r'^Certificate Authority is revoked\.$'
        ), self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=self.ca, subject=subject, stdin=stdin)
        self.assertFalse(pre.called)
        self.assertFalse(post.called)

    @override_tmpcadir()
    @freeze_time(timestamps['everything_valid'])
    def test_unusable_ca(self):
        """Test signing with an unusable CA."""
        path = ca_storage.path(self.ca.private_key_path)
        os.remove(path)
        msg = r"^\[Errno 2\] No such file or directory: u?'%s'" % path
        stdin = StringIO(self.csr_pem)
        subject = Subject([('CN', 'example.com')])

        with self.assertCommandError(msg), \
                self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=self.ca, subject=subject, stdin=stdin)
        self.assertFalse(pre.called)
        self.assertFalse(post.called)

    @override_tmpcadir()
    @freeze_time(timestamps['everything_expired'])
    def test_expired_ca(self):
        """Test signing with an expired CA."""
        stdin = StringIO(self.csr_pem)
        subject = Subject([('CN', 'example.com')])

        with self.assertCommandError(
                r'^Certificate Authority has expired\.$'
        ), self.assertSignal(pre_issue_cert) as pre, self.assertSignal(post_issue_cert) as post:
            self.cmd('sign_cert', ca=self.ca, subject=subject, stdin=stdin)
        self.assertFalse(pre.called)
        self.assertFalse(post.called)


@override_settings(USE_TZ=True)
class SignCertWithTZTestCase(SignCertTestCase):
    """Same but with timezone support."""
