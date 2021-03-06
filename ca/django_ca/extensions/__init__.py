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

"""Extension classes wrapping various X.509 extensions.

The classes in this module wrap cryptography extensions, but allow adding/removing values, creating extensions
in a more pythonic manner and provide access functions."""

# pylint: disable=unsubscriptable-object; https://github.com/PyCQA/pylint/issues/3882

import re
from typing import Dict
from typing import Type
from typing import Union
from typing import cast

from cryptography import x509

from .base import Extension
from .extensions import AuthorityInformationAccess
from .extensions import AuthorityKeyIdentifier
from .extensions import BasicConstraints
from .extensions import CertificatePolicies
from .extensions import CRLDistributionPoints
from .extensions import ExtendedKeyUsage
from .extensions import FreshestCRL
from .extensions import InhibitAnyPolicy
from .extensions import IssuerAlternativeName
from .extensions import KeyUsage
from .extensions import NameConstraints
from .extensions import OCSPNoCheck
from .extensions import PolicyConstraints
from .extensions import PrecertificateSignedCertificateTimestamps
from .extensions import PrecertPoison
from .extensions import SubjectAlternativeName
from .extensions import SubjectKeyIdentifier
from .extensions import TLSFeature

KEY_TO_EXTENSION: Dict[str, Type[Extension]] = {
    AuthorityInformationAccess.key: AuthorityInformationAccess,
    AuthorityKeyIdentifier.key: AuthorityKeyIdentifier,
    BasicConstraints.key: BasicConstraints,
    CRLDistributionPoints.key: CRLDistributionPoints,
    CertificatePolicies.key: CertificatePolicies,
    ExtendedKeyUsage.key: ExtendedKeyUsage,
    FreshestCRL.key: FreshestCRL,
    InhibitAnyPolicy.key: InhibitAnyPolicy,
    IssuerAlternativeName.key: IssuerAlternativeName,
    KeyUsage.key: KeyUsage,
    NameConstraints.key: NameConstraints,
    OCSPNoCheck.key: OCSPNoCheck,
    PolicyConstraints.key: PolicyConstraints,
    PrecertPoison.key: PrecertPoison,
    PrecertificateSignedCertificateTimestamps.key: PrecertificateSignedCertificateTimestamps,
    SubjectAlternativeName.key: SubjectAlternativeName,
    SubjectKeyIdentifier.key: SubjectKeyIdentifier,
    TLSFeature.key: TLSFeature,
}

OID_TO_EXTENSION: Dict[x509.ObjectIdentifier, Type[Extension]] = {e.oid: e for e in KEY_TO_EXTENSION.values()}


def get_extension_name(ext: Union[x509.Extension, Extension]) -> str:
    """Function to get the name of an extension.

    >>> ext = x509.BasicConstraints(ca=True, path_length=3)
    >>> get_extension_name(ext)
    'BasicConstraints'
    """

    if ext.oid in OID_TO_EXTENSION:
        return OID_TO_EXTENSION[ext.oid].name

    # pylint: disable=protected-access; there is no other way to get a human-readable name
    oid_name = cast(str, ext.oid._name)  # type: ignore

    return re.sub('^([a-z])', lambda x: x.groups()[0].upper(), oid_name)


__all__ = [
    'get_extension_name',
] + [c.__name__ for c in KEY_TO_EXTENSION.values()]
