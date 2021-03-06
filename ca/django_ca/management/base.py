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
# see <http://www.gnu.org/licenses/>.

"""Command subclasses and argparse helpers for django-ca."""

import sys
from textwrap import indent

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand as _BaseCommand
from django.core.management.base import CommandError
from django.core.management.base import OutputWrapper
from django.core.management.color import no_style
from django.utils import timezone
from django.utils.encoding import force_bytes

from .. import ca_settings
from ..extensions import ExtendedKeyUsage
from ..extensions import Extension
from ..extensions import IssuerAlternativeName
from ..extensions import KeyUsage
from ..extensions import SubjectAlternativeName
from ..extensions import TLSFeature
from ..extensions.base import NullExtension
from ..models import CertificateAuthority
from ..utils import SUBJECT_FIELDS
from ..utils import add_colons
from . import actions


class BinaryOutputWrapper(OutputWrapper):
    """An output wrapper that allows you to write binary data."""

    def __init__(self, out, ending=b'\n'):
        super().__init__(out, ending=ending)

    def write(self, msg=b'', style_func=None, ending=None):
        ending = self.ending if ending is None else ending
        msg = force_bytes(msg)

        if ending and not msg.endswith(ending):
            msg += ending
        self._out.write(msg)


class BaseCommand(_BaseCommand):  # pylint: disable=abstract-method; is a base class
    """Base class for most/all management commands."""
    binary_output = False

    def __init__(self, stdout=None, stderr=None, no_color=False):
        if self.binary_output is True:
            self.stdout = BinaryOutputWrapper(stdout or sys.stdout.buffer)
            self.stderr = BinaryOutputWrapper(stderr or sys.stderr.buffer)
            self.style = no_style()
        else:
            super().__init__(stdout, stderr, no_color=no_color)

    def dump(self, path, data):
        """Dump `data` to `path` (``-`` means stdout)."""

        if path == '-':
            self.stdout.write(data, ending=b'')
        else:
            try:
                with open(path, 'wb') as stream:
                    stream.write(data)
            except IOError as ex:
                raise CommandError(ex) from ex

    def execute(self, *args, **options):
        if self.binary_output is True:
            if options.get('stdout'):  # pragma: no branch
                self.stdout = BinaryOutputWrapper(options.pop('stdout'))
            if options.get('stderr'):  # pragma: no branch
                self.stderr = BinaryOutputWrapper(options.pop('stderr'))
            options['no_color'] = True

        super().execute(*args, **options)

    def add_algorithm(self, parser):
        """Add the --algorithm option."""

        help_text = 'The HashAlgorithm that will be used to generate the signature (default: %s).' % (
            ca_settings.CA_DIGEST_ALGORITHM.name)

        parser.add_argument(
            '--algorithm', metavar='{sha512,sha256,...}', default=ca_settings.CA_DIGEST_ALGORITHM,
            action=actions.AlgorithmAction, help=help_text)

    @property
    def valid_subject_keys(self):
        """Return human-readable enumeration of valid subject keys (CN/...)."""
        fields = ['"%s"' % f for f in SUBJECT_FIELDS]
        return '%s and %s' % (', '.join(fields[:-1]), fields[-1])

    def add_subject(self, parser, arg='subject', metavar=None, help_text=None):
        """Add subject option."""
        parser.add_argument(arg, action=actions.SubjectAction, metavar=metavar, help=help_text)

    def add_ca(self, parser, arg='--ca', help_text='Certificate authority to use (default: %(default)s).',
               allow_disabled=False, no_default=False, allow_unusable=False):
        """Add the ``--ca`` action.

        Parameters
        ----------

        parser
        arg : str, optional
        help : str, optional
        allow_disabled : bool, optional
        no_default : bool, optional
        allow_unusable : bool, optional
        """
        if no_default is True:
            default = None
        else:
            try:
                default = CertificateAuthority.objects.default()
            except ImproperlyConfigured:
                default = None

        help_text = help_text % {'default': add_colons(default.serial) if default else None}
        parser.add_argument('%s' % arg, metavar='SERIAL', help=help_text, default=default,
                            allow_disabled=allow_disabled, allow_unusable=allow_unusable,
                            action=actions.CertificateAuthorityAction)

    def add_ecc_curve(self, parser):
        """Add --ecc-curve option."""
        curve_help = 'Elliptic Curve used for ECC keys (default: %(default)s).' % {
            'default': ca_settings.CA_DEFAULT_ECC_CURVE.__class__.__name__,
        }
        parser.add_argument('--ecc-curve', metavar='CURVE', action=actions.KeyCurveAction,
                            default=ca_settings.CA_DEFAULT_ECC_CURVE,
                            help=curve_help)

    def add_format(self, parser, default=Encoding.PEM, help_text=None, opts=None):
        """Add the --format option."""

        if opts is None:
            opts = ['-f', '--format']
        if help_text is None:
            help_text = 'The format to use ("ASN1" is an alias for "DER", default: %(default)s).'
        help_text = help_text % {'default': default.name}
        parser.add_argument(*opts, metavar='{PEM,ASN1,DER}', default=default,
                            action=actions.FormatAction, help=help_text)

    def add_key_size(self, parser):
        """Add --key-size option (2048, 4096, ...)."""
        parser.add_argument(
            '--key-size', action=actions.KeySizeAction, default=ca_settings.CA_DEFAULT_KEY_SIZE,
            help="Key size for the private key (default: %(default)s).")

    def add_key_type(self, parser):
        """Add --key-type option (type of private key - RSA/DSA/ECC)."""
        parser.add_argument(
            '--key-type', choices=['RSA', 'DSA', 'ECC'], default='RSA',
            help="Key type for the private key (default: %(default)s).")

    def add_password(self, parser, help_text=None):
        """Add password option."""
        if help_text is None:
            help_text = 'Password used for accessing the private key of the CA.'
        parser.add_argument('-p', '--password', nargs='?', action=actions.PasswordAction, help=help_text)

    def add_profile(self, parser, help_text):
        """Add profile-related options."""
        group = parser.add_argument_group('profiles', help_text)
        group = group.add_mutually_exclusive_group()
        for name, profile in ca_settings.CA_PROFILES.items():
            group.add_argument('--%s' % name, action='store_const', const=name, dest='profile',
                               help=profile.get('description', ''))

    def indent(self, text, prefix='    '):
        """Get indented text."""
        return indent(text, prefix)

    def print_extension(self, ext):
        """Print extension to stdout."""

        if isinstance(ext, Extension):
            if isinstance(ext, NullExtension):
                if ext.critical:
                    # NOTE: Only PrecertPoison is ever marked as critical
                    self.stdout.write('%s (critical): Yes' % ext.name)
                else:
                    self.stdout.write('%s: Yes' % ext.name)
            else:
                if ext.critical:
                    self.stdout.write('%s (critical):' % ext.name)
                else:
                    self.stdout.write('%s:' % ext.name)

                self.stdout.write(self.indent(ext.as_text()))
        elif isinstance(ext, x509.Extension):
            oid_name = ext.oid._name  # pylint: disable=protected-access; only wai to get name
            if ext.critical:  # pragma: no cover - all unrecognized extensions that we have are non-critical
                self.stdout.write('%s (critical): %s' % (oid_name, ext.oid.dotted_string))
            else:
                self.stdout.write('%s: %s' % (oid_name, ext.oid.dotted_string))
        else:  # pragma: no cover
            raise ValueError('Received unknown extension type: %s' % type(ext))

    def print_extensions(self, cert):
        """Print all extensions for the given certificate."""
        for ext in cert.extensions:
            self.print_extension(ext)

    def test_private_key(self, ca, password):
        """Test that we can load the private key of a CA."""
        try:
            ca.key(password)
        except Exception as ex:
            raise CommandError(str(ex)) from ex


class BaseSignCommand(BaseCommand):  # pylint: disable=abstract-method; is a base class
    """Base class for commands signing certificates (sign_cert, resign_cert)."""

    add_extensions_help = None  # concrete classes should set this
    sign_extensions = {
        SubjectAlternativeName,
        KeyUsage,
        ExtendedKeyUsage,
        TLSFeature,
    }
    subject_help = None  # concrete classes should set this

    def add_base_args(self, parser, no_default_ca=False):
        """Add common arguments for signing certificates."""
        self.add_subject_group(parser)
        self.add_algorithm(parser)
        self.add_ca(parser, no_default=no_default_ca)
        self.add_password(parser)
        self.add_extensions(parser)

        parser.add_argument(
            '--expires', default=ca_settings.CA_DEFAULT_EXPIRES, action=actions.ExpiresAction,
            help='Sign the certificate for DAYS days (default: %(default)s)')
        parser.add_argument(
            '--alt', metavar='DOMAIN', action=actions.AlternativeNameAction, extension=SubjectAlternativeName,
            help='Add a subjectAltName to the certificate (may be given multiple times)')
        parser.add_argument(
            '--watch', metavar='EMAIL', action='append', default=[],
            help='Email EMAIL when this certificate expires (may be given multiple times)')
        parser.add_argument(
            '--out', metavar='FILE',
            help='Save signed certificate to FILE. If omitted, print to stdout.')

    def add_subject_group(self, parser):
        """Add argument for a subject."""

        group = parser.add_argument_group('Certificate subject', self.subject_help)

        # NOTE: Don't set the default value here because it would mask the user not setting anything at all.
        self.add_subject(
            group, arg='--subject', metavar='/key1=value1/key2=value2/...',
            help_text='''Valid keys are %s. Pass an empty value (e.g. "/C=/ST=...") to remove a field
                      from the subject.''' % self.valid_subject_keys)

    def add_extensions(self, parser):
        """Add arguments for x509 extensions."""
        group = parser.add_argument_group('X509 v3 certificate extensions', self.add_extensions_help)
        group.add_argument(
            '--key-usage', metavar='VALUES', action=actions.OrderedSetExtensionAction, extension=KeyUsage,
            help='The keyUsage extension, e.g. "critical,keyCertSign".')
        group.add_argument(
            '--ext-key-usage', metavar='VALUES', action=actions.OrderedSetExtensionAction,
            extension=ExtendedKeyUsage,
            help='The extendedKeyUsage extension, e.g. "serverAuth,clientAuth".')
        group.add_argument(
            '--tls-feature', metavar='VALUES', action=actions.OrderedSetExtensionAction, extension=TLSFeature,
            help='TLS Feature extensions.')

    def test_options(self, *args, **options):  # pylint: disable=unused-argument; args may be used in future
        """Additional tests for validity of some options."""

        ca = options['ca']
        if ca.expires < timezone.now() + options['expires']:
            max_days = (ca.expires - timezone.now()).days
            raise CommandError(
                'Certificate would outlive CA, maximum expiry for this CA is %s days.' % max_days)

        # See if we can work with the private key
        self.test_private_key(ca, options['password'])


class CertCommand(BaseCommand):  # pylint: disable=abstract-method; is a base class
    """Base class for commands that operate on a single certificate."""

    allow_revoked = False

    def add_arguments(self, parser):
        parser.add_argument(
            'cert', action=actions.CertificateAction, allow_revoked=self.allow_revoked,
            help='''Certificate by CommonName or serial. If you give a CommonName (which is not by
                definition unique) there must be only one valid certificate with the given
                CommonName.''')
        super().add_arguments(parser)


class CertificateAuthorityDetailMixin:
    """Mixin to add common arguments to init_ca and edit_ca."""

    def add_general_args(self, parser, default=''):
        """Add some general arguments."""

        group = parser.add_argument_group('General', 'General information about the CA.')
        group.add_argument('--caa', default=default, metavar='NAME', help='CAA record for this CA.')
        group.add_argument('--website', default=default, metavar='URL', action=actions.URLAction,
                           help='Browsable URL for the CA.')
        group.add_argument('--tos', default=default, metavar='URL', action=actions.URLAction,
                           help='Terms of service URL for the CA.')

    def add_acme_group(self, parser):
        """Add arguments for ACMEv2."""

        if not ca_settings.CA_ENABLE_ACME:
            return

        group = parser.add_argument_group('ACMEv2', 'ACMEv2 configuration.')

        enable_group = group.add_mutually_exclusive_group()
        enable_group.add_argument('--acme-enable', dest='acme_enabled', action='store_true', default=None,
                                  help="Enable ACMEv2 support.")
        enable_group.add_argument('--acme-disable', dest='acme_enabled', action='store_false',
                                  help='Disable ACMEv2 support.')

        disable_group = group.add_mutually_exclusive_group()
        disable_group.add_argument(
            '--acme-contact-optional', dest='acme_requires_contact', action='store_false', default=None,
            help="Do not require email address during ACME account registration.")

        disable_group.add_argument(
            '--acme-contact-required', dest='acme_requires_contact', action='store_true',
            help="Require email address during ACME account registration.")

    def add_ca_args(self, parser):
        """Add CA arguments."""

        group = parser.add_argument_group(
            'X509 v3 certificate extensions for signed certificates',
            'Extensions added when signing certificates.')
        group.add_argument('--issuer-url', metavar='URL', action=actions.URLAction,
                           help='URL to the certificate of your CA (in DER format).')
        group.add_argument(
            '--issuer-alt-name', metavar='URL', action=actions.AlternativeNameAction,
            extension=IssuerAlternativeName, help='URL to the homepage of your CA.'
        )
        group.add_argument(
            '--crl-url', action=actions.MultipleURLAction,
            help='URL to a certificate revokation list. Can be given multiple times.'
        )
        group.add_argument('--ocsp-url', metavar='URL', action=actions.URLAction,
                           help='URL of an OCSP responder.')
