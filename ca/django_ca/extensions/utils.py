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

"""``django_ca.extensions.utils`` contains various utility classes used by X.509 extensions."""

# pylint: disable=unsubscriptable-object; https://github.com/PyCQA/pylint/issues/3882

import textwrap
from typing import Any
from typing import Dict
from typing import FrozenSet
from typing import Iterable
from typing import List
from typing import Optional
from typing import Union
from typing import cast

from cryptography import x509
from cryptography.x509.oid import ObjectIdentifier

from django.utils.encoding import force_str

from ..typehints import ParsablePolicyIdentifier
from ..typehints import ParsablePolicyInformation
from ..typehints import ParsablePolicyQualifier
from ..typehints import PolicyQualifier
from ..typehints import SerializedPolicyQualifier
from ..typehints import SerializedPolicyQualifiers
from ..utils import GeneralNameList
from ..utils import format_relative_name
from ..utils import x509_relative_name


class DistributionPoint:
    """Class representing a Distribution Point.

    This class is used internally by extensions that have a list of Distribution Points, e.g. the :
    :py:class:`~django_ca.extensions.CRLDistributionPoints` extension. The class accepts either a
    :py:class:`cg:cryptography.x509.DistributionPoint` or a ``dict``. Note that in the latter case, you can
    also pass a ``str`` as ``full_name`` or ``crl_issuer`` if there is only one value::

        >>> DistributionPoint(x509.DistributionPoint(
        ...     full_name=[x509.UniformResourceIdentifier('http://ca.example.com/crl')],
        ...     relative_name=None, crl_issuer=None, reasons=None
        ... ))
        <DistributionPoint: full_name=['URI:http://ca.example.com/crl']>
        >>> DistributionPoint({'full_name': ['http://example.com']})
        <DistributionPoint: full_name=['URI:http://example.com']>
        >>> DistributionPoint({'full_name': 'http://example.com'})
        <DistributionPoint: full_name=['URI:http://example.com']>
        >>> DistributionPoint({
        ...     'relative_name': '/CN=example.com',
        ...     'crl_issuer': 'http://example.com',
        ...     'reasons': ['key_compromise', 'ca_compromise'],
        ... })  # doctest: +NORMALIZE_WHITESPACE
        <DistributionPoint: relative_name='/CN=example.com', crl_issuer=['URI:http://example.com'],
                            reasons=['ca_compromise', 'key_compromise']>

    .. seealso::

        `RFC 5280, section 4.2.1.13 <https://tools.ietf.org/html/rfc5280#section-4.2.1.13>`_
    """

    full_name: Optional[GeneralNameList] = None
    relative_name: Optional[x509.RelativeDistinguishedName] = None
    crl_issuer: Optional[GeneralNameList] = None
    reasons: Optional[FrozenSet[x509.ReasonFlags]] = None

    def __init__(self, data: Union[x509.DistributionPoint, Dict[str, Any]] = None) -> None:
        if data is None:
            data = {}

        if isinstance(data, x509.DistributionPoint):
            self.full_name = GeneralNameList.get_from_value(data.full_name)
            self.relative_name = data.relative_name
            self.crl_issuer = GeneralNameList.get_from_value(data.crl_issuer)
            self.reasons = data.reasons
        elif isinstance(data, dict):
            self.full_name = GeneralNameList.get_from_value(data.get('full_name'))
            self.relative_name = data.get('relative_name')
            self.crl_issuer = GeneralNameList.get_from_value(data.get('crl_issuer'))
            self.reasons = data.get('reasons')

            if self.full_name is not None and self.relative_name is not None:
                raise ValueError('full_name and relative_name cannot both have a value')

            if self.relative_name is not None:
                self.relative_name = x509_relative_name(self.relative_name)
            if self.reasons is not None:
                self.reasons = frozenset([x509.ReasonFlags[r] for r in self.reasons])
        else:
            raise ValueError('data must be x509.DistributionPoint or dict')

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, DistributionPoint) and self.full_name == other.full_name \
            and self.relative_name == other.relative_name and self.crl_issuer == other.crl_issuer \
            and self.reasons == other.reasons

    def __get_values(self) -> List[str]:
        values: List[str] = []
        if self.full_name is not None:
            values.append('full_name=%r' % list(self.full_name.serialize()))
        if self.relative_name:
            values.append("relative_name='%s'" % format_relative_name(self.relative_name))
        if self.crl_issuer is not None:
            values.append('crl_issuer=%r' % list(self.crl_issuer.serialize()))
        if self.reasons:
            values.append('reasons=%s' % sorted([r.name for r in self.reasons]))
        return values

    def __hash__(self) -> int:
        full_name = tuple(self.full_name) if self.full_name is not None else None
        crl_issuer = tuple(self.crl_issuer) if self.crl_issuer is not None else None
        reasons = tuple(self.reasons) if self.reasons else None
        return hash((full_name, self.relative_name, crl_issuer, reasons))

    def __repr__(self) -> str:
        return '<DistributionPoint: %s>' % ', '.join(self.__get_values())

    def __str__(self) -> str:
        return repr(self)

    def as_text(self) -> str:
        """Show as text."""
        if self.full_name is not None:
            names = [textwrap.indent('* %s' % s, '  ') for s in self.full_name.serialize()]
            text = '* Full Name:\n%s' % '\n'.join(names)
        elif self.relative_name is not None:  # pragma: no branch
            text = '* Relative Name: %s' % format_relative_name(self.relative_name)

        if self.crl_issuer is not None:
            names = [textwrap.indent('* %s' % s, '  ') for s in self.crl_issuer.serialize()]
            text += '\n* CRL Issuer:\n%s' % '\n'.join(names)
        if self.reasons:
            text += '\n* Reasons: %s' % ', '.join(sorted([r.name for r in self.reasons]))
        return text

    @property
    def for_extension_type(self) -> x509.DistributionPoint:
        """Convert instance to a suitable cryptography class."""
        return x509.DistributionPoint(full_name=self.full_name, relative_name=self.relative_name,
                                      crl_issuer=self.crl_issuer, reasons=self.reasons)

    def serialize(self) -> Dict[str, Union[List[str], str]]:
        """Serialize this distribution point."""
        val: Dict[str, Union[List[str], str]] = {}

        if self.full_name is not None:
            val['full_name'] = list(self.full_name.serialize())
        if self.relative_name is not None:
            val['relative_name'] = format_relative_name(self.relative_name)
        if self.crl_issuer is not None:
            val['crl_issuer'] = list(self.crl_issuer.serialize())
        if self.reasons is not None:
            val['reasons'] = list(sorted([r.name for r in self.reasons]))
        return val


class PolicyInformation:
    """Class representing a PolicyInformation object.

    This class is internally used by the :py:class:`~django_ca.extensions.CertificatePolicies` extension.

    You can pass a :py:class:`~cg:cryptography.x509.PolicyInformation` instance or a dictionary representing
    that instance::

        >>> PolicyInformation({'policy_identifier': '2.5.29.32.0', 'policy_qualifiers': ['text1']})
        <PolicyInformation(oid=2.5.29.32.0, qualifiers=['text1'])>
        >>> PolicyInformation({
        ...     'policy_identifier': '2.5.29.32.0',
        ...     'policy_qualifiers': [{'explicit_text': 'text2', }],
        ... })
        <PolicyInformation(oid=2.5.29.32.0, qualifiers=[{'explicit_text': 'text2'}])>
        >>> PolicyInformation({
        ...     'policy_identifier': '2.5',
        ...     'policy_qualifiers': [{
        ...         'notice_reference': {
        ...             'organization': 't3',
        ...             'notice_numbers': [1, ],
        ...         }
        ...     }],
        ... })  # doctest: +ELLIPSIS
        <PolicyInformation(oid=2.5, qualifiers=[{'notice_reference': {...}}])>
    """

    _policy_identifier: Optional[x509.ObjectIdentifier]
    policy_qualifiers: Optional[List[PolicyQualifier]]

    def __init__(
            self, data: Optional[Union[x509.PolicyInformation, ParsablePolicyInformation]] = None
    ) -> None:
        if isinstance(data, x509.PolicyInformation):
            self.policy_identifier = data.policy_identifier
            self.policy_qualifiers = data.policy_qualifiers
        elif isinstance(data, dict):
            self.policy_identifier = cast(ParsablePolicyIdentifier, data['policy_identifier'])
            self.policy_qualifiers = self.parse_policy_qualifiers(
                cast(Iterable[ParsablePolicyQualifier], data.get('policy_qualifiers'))
            )
        elif data is None:
            self.policy_identifier = None
            self.policy_qualifiers = None
        else:
            raise ValueError('PolicyInformation data must be either x509.PolicyInformation or dict')

    def __contains__(self, value: ParsablePolicyQualifier) -> bool:
        if self.policy_qualifiers is None:
            return False
        return self._parse_policy_qualifier(value) in self.policy_qualifiers

    def __delitem__(self, key: Union[int, slice]) -> None:
        if self.policy_qualifiers is None:
            raise IndexError('list assignment index out of range')
        del self.policy_qualifiers[key]
        if not self.policy_qualifiers:
            self.policy_qualifiers = None

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, PolicyInformation) and self.policy_identifier == other.policy_identifier \
            and self.policy_qualifiers == other.policy_qualifiers

    def __getitem__(
            self, key: Union[int, slice]
    ) -> Union[List[SerializedPolicyQualifier], SerializedPolicyQualifier]:
        """Implement item getter (e.g ``pi[0]`` or ``pi[0:1]``)."""

        if self.policy_qualifiers is None:
            raise IndexError('list index out of range')
        if isinstance(key, int):
            return self._serialize_policy_qualifier(self.policy_qualifiers[key])

        return [self._serialize_policy_qualifier(k) for k in self.policy_qualifiers[key]]

    def __hash__(self) -> int:
        if self.policy_qualifiers is None:
            tup = None
        else:
            tup = tuple(self.policy_qualifiers)

        return hash((self.policy_identifier, tup))

    def __len__(self) -> int:
        if self.policy_qualifiers is None:
            return 0
        return len(self.policy_qualifiers)

    def __repr__(self) -> str:
        if self.policy_identifier is None:
            ident = 'None'
        else:
            ident = self.policy_identifier.dotted_string

        return '<PolicyInformation(oid=%s, qualifiers=%r)>' % (ident, self.serialize_policy_qualifiers())

    def __str__(self) -> str:
        return repr(self)

    def append(self, value: ParsablePolicyQualifier) -> None:
        """Append the given policy qualifier."""
        if self.policy_qualifiers is None:
            self.policy_qualifiers = []
        self.policy_qualifiers.append(self._parse_policy_qualifier(value))

    def as_text(self, width: int = 76) -> str:
        """Show as text."""
        if self.policy_identifier is None:
            text = 'Policy Identifier: %s\n' % None
        else:
            text = 'Policy Identifier: %s\n' % self.policy_identifier.dotted_string

        if self.policy_qualifiers:
            text += 'Policy Qualifiers:\n'
            for qualifier in self.policy_qualifiers:
                if isinstance(qualifier, str):
                    lines = textwrap.wrap(qualifier, initial_indent='* ', subsequent_indent='  ', width=width)
                    text += '%s\n' % '\n'.join(lines)
                else:
                    text += '* UserNotice:\n'
                    if qualifier.explicit_text:
                        text += '\n'.join(textwrap.wrap(
                            'Explicit text: %s\n' % qualifier.explicit_text,
                            initial_indent='  * ', subsequent_indent='    ', width=width - 2
                        )) + '\n'
                    if qualifier.notice_reference:
                        text += '  * Reference:\n'
                        text += '    * Organiziation: %s\n' % qualifier.notice_reference.organization
                        text += '    * Notice Numbers: %s\n' % qualifier.notice_reference.notice_numbers
        else:
            text += 'No Policy Qualifiers'

        return text.strip()

    def clear(self) -> None:
        """Clear all qualifiers from this information."""
        self.policy_qualifiers = None

    def count(self, value: ParsablePolicyQualifier) -> int:
        """Count qualifiers from this information."""
        if self.policy_qualifiers is None:
            return 0

        try:
            parsed_value = self._parse_policy_qualifier(value)
        except ValueError:
            return 0

        return self.policy_qualifiers.count(parsed_value)

    def extend(self, value: Iterable[ParsablePolicyQualifier]) -> None:
        """Extend qualifiers with given iterable."""
        if self.policy_qualifiers is None:
            self.policy_qualifiers = []

        self.policy_qualifiers.extend([self._parse_policy_qualifier(v) for v in value])

    @property
    def for_extension_type(self) -> x509.PolicyInformation:
        """Convert instance to a suitable cryptography class."""
        return x509.PolicyInformation(policy_identifier=self.policy_identifier,
                                      policy_qualifiers=self.policy_qualifiers)

    def insert(self, index: int, value: ParsablePolicyQualifier) -> None:
        """Insert qualifier at given index."""
        if self.policy_qualifiers is None:
            self.policy_qualifiers = []
        self.policy_qualifiers.insert(index, self._parse_policy_qualifier(value))

    def _parse_policy_qualifier(self, qualifier: ParsablePolicyQualifier) -> PolicyQualifier:

        if isinstance(qualifier, str):
            return qualifier
        if isinstance(qualifier, x509.UserNotice):
            return qualifier
        if isinstance(qualifier, dict):
            explicit_text = qualifier.get('explicit_text')

            notice_reference = qualifier.get('notice_reference')
            if isinstance(notice_reference, dict):
                notice_reference = x509.NoticeReference(
                    organization=force_str(notice_reference.get('organization', '')),
                    notice_numbers=[int(i) for i in notice_reference.get('notice_numbers', [])]
                )
            elif notice_reference is None:
                pass  # extra branch to ensure test coverage
            elif isinstance(notice_reference, x509.NoticeReference):
                pass  # extra branch to ensure test coverage
            else:
                raise ValueError('NoticeReference must be either None, a dict or an x509.NoticeReference')

            return x509.UserNotice(explicit_text=explicit_text, notice_reference=notice_reference)
        raise ValueError('PolicyQualifier must be string, dict or x509.UserNotice')

    def parse_policy_qualifiers(
            self, qualifiers: Optional[Iterable[ParsablePolicyQualifier]]
    ) -> Optional[List[PolicyQualifier]]:
        """Parse given list of policy qualifiers."""
        if qualifiers is None:
            return None
        return [self._parse_policy_qualifier(q) for q in qualifiers]

    def get_policy_identifier(self) -> Optional[x509.ObjectIdentifier]:
        """Property for the policy identifier.

        Note that you can set any parseable value, it will always be an object identifier::

            >>> pi = PolicyInformation()
            >>> pi.policy_identifier = '1.2.3'
            >>> pi.policy_identifier
            <ObjectIdentifier(oid=1.2.3, name=Unknown OID)>
        """
        return self._policy_identifier

    def _set_policy_identifier(self, value: ParsablePolicyIdentifier) -> None:
        if isinstance(value, str):
            self._policy_identifier = ObjectIdentifier(value)
        else:
            self._policy_identifier = value

    policy_identifier = property(get_policy_identifier, _set_policy_identifier)

    def pop(self, index: int = -1) -> SerializedPolicyQualifier:
        """Pop qualifier from given index."""
        if self.policy_qualifiers is None:
            return [].pop()

        val = self._serialize_policy_qualifier(self.policy_qualifiers.pop(index))

        if not self.policy_qualifiers:  # if list is now empty, set to none
            self.policy_qualifiers = None

        return val

    def remove(self, value: ParsablePolicyQualifier) -> PolicyQualifier:
        """Remove the given qualifier from this policy information.

        Note that unlike list.remove(), this value returns the parsed value.
        """
        if self.policy_qualifiers is None:
            # Shortcut to raise the same Value error as if the element is not in the list
            raise ValueError('%s: not in list.' % value)

        parsed_value = self._parse_policy_qualifier(value)
        self.policy_qualifiers.remove(parsed_value)

        if not self.policy_qualifiers:  # if list is now empty, set to none
            self.policy_qualifiers = None

        return parsed_value

    def _serialize_policy_qualifier(self, qualifier: PolicyQualifier) -> SerializedPolicyQualifier:
        if isinstance(qualifier, str):
            return qualifier

        value = {}
        if qualifier.explicit_text:
            value['explicit_text'] = qualifier.explicit_text

        if qualifier.notice_reference:
            value['notice_reference'] = {
                'notice_numbers': qualifier.notice_reference.notice_numbers,
                'organization': qualifier.notice_reference.organization,
            }
        return value

    def serialize_policy_qualifiers(self) -> SerializedPolicyQualifiers:
        """Serialize policy qualifiers."""
        if self.policy_qualifiers is None:
            return None

        return [self._serialize_policy_qualifier(q) for q in self.policy_qualifiers]

    def serialize(self) -> Dict[str, Union[str, SerializedPolicyQualifiers]]:
        """Serialize this policy information."""
        value = {
            'policy_identifier': self.policy_identifier.dotted_string,
        }
        qualifiers = self.serialize_policy_qualifiers()
        if qualifiers:
            value['policy_qualifiers'] = qualifiers

        return value
