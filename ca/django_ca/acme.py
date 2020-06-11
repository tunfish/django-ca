# This file is part of django-ca (https://github.com/mathiasertl/django-ca).
#
# django-ca is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# django-ca is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
# for more details.
#
# You should have received a copy of the GNU General Public License along with django-ca. If not, see
# <http://www.gnu.org/licenses/>.

from http import HTTPStatus

from acme.messages import Order

from django.http import JsonResponse
from django.urls import reverse


class AcmeResponse(JsonResponse):
    pass


class AcmeResponseAccountCreated(AcmeResponse):
    status_code = HTTPStatus.CREATED

    def __init__(self, request, account):
        data = {
            'status': account.status,
            'contanct': [account.contact],
            'orders': request.build_absolute_uri(
                reverse('django_ca:acme-account-orders', kwargs={'pk': account.pk})),
        }

        super().__init__(data)

        self['Location'] = request.build_absolute_uri(
            reverse('django_ca:acme-account', kwargs={'pk': account.pk}))


class AcmeResponseOrderCreated(AcmeResponse):
    status_code = HTTPStatus.CREATED

    def __init__(self, **kwargs):
        super().__init__(Order(**kwargs).to_json())


class AcmeResponseError(AcmeResponse):
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    type = 'serverInternal'
    message = ''

    def __init__(self, message=''):
        details = {
            'type': 'urn:ietf:params:acme:error:%s' % self.type,
            'status': self.status_code,
        }

        message = message or self.message
        if message:
            details['detail'] = message

        super().__init__(details, content_type='application/problem+json')


class AcmeResponseMalformed(AcmeResponseError):
    status_code = HTTPStatus.BAD_REQUEST  # 400
    type = 'malformed'


class AcmeResponseUnauthorized(AcmeResponseError):
    status_code = HTTPStatus.UNAUTHORIZED  # 401
    type = 'unauthorized'
    message = "You are not authorized to perform this request."


class AcmeResponseBadNonce(AcmeResponseError):
    """

    .. seealso:: RFC 8555, section 6.5:

       "When a server rejects a request because its nonce value was unacceptable (or not present), it MUST
       provide HTTP status code 400 (Bad Request), and indicate the ACME error type
       "urn:ietf:params:acme:error:badNonce".  An error response with the "badNonce" error type MUST include a
       Replay-Nonce header field with a fresh nonce that the server will accept in a retry of the original
       query (and possibly in other requests, according to the server's nonce scoping policy)."
    """
    status_code = HTTPStatus.BAD_REQUEST  # 400
    type = 'badNonce'
    message = "Bad or invalid nonce."


class AcmeResponseUnsupportedMediaType(AcmeResponseMalformed):
    status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    message = 'Requests must use the application/jose+json content type.'


class AcmeException(Exception):
    response = AcmeResponseError

    def get_response(self):
        return self.response(*self.args)


class AcmeMalformed(AcmeException):
    response = AcmeResponseMalformed