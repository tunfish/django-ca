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

"""Test ACME related views."""

import json
from datetime import datetime
from http import HTTPStatus
from unittest import mock

from django.core.cache import cache
from django.urls import reverse

from freezegun import freeze_time

from ..models import CertificateAuthority
from .base import DjangoCAWithCATestCase
from .base import override_settings
from .base import timestamps


class DirectoryTestCase(DjangoCAWithCATestCase):
    """Test basic ACMEv2 directory view."""
    url = reverse('django_ca:acme-directory')

    def test_default(self):
        """Test the default directory view."""
        with mock.patch('secrets.token_bytes', return_value=b'foobar'):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        ca = CertificateAuthority.objects.default()
        req = response.wsgi_request
        self.assertEqual(response.json(), {
            'Zm9vYmFy': 'https://community.letsencrypt.org/t/adding-random-entries-to-the-directory/33417',
            'keyChange': 'http://localhost:8000/django_ca/acme/todo/key-change',
            'revokeCert': 'http://localhost:8000/django_ca/acme/todo/revoke-cert',
            'newAccount': req.build_absolute_uri('/django_ca/acme/%s/new-account/' % ca.serial),
            'newNonce': req.build_absolute_uri('/django_ca/acme/%s/new-nonce/' % ca.serial),
            'newOrder': req.build_absolute_uri('/django_ca/acme/%s/new-order/' % ca.serial),
            'meta': {
                "termsOfService": "https://localhost:8000/django_ca/example.pdf",
                "website": "https://localhost:8000",
            }
        })

    def test_named_ca(self):
        """Test getting directory for named CA."""

        ca = CertificateAuthority.objects.default()
        url = reverse('django_ca:acme-directory', kwargs={'serial': ca.serial})
        with mock.patch('secrets.token_bytes', return_value=b'foobar'):
            response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response['Content-Type'], 'application/json')
        req = response.wsgi_request
        self.assertEqual(response.json(), {
            'Zm9vYmFy': 'https://community.letsencrypt.org/t/adding-random-entries-to-the-directory/33417',
            'keyChange': 'http://localhost:8000/django_ca/acme/todo/key-change',
            'revokeCert': 'http://localhost:8000/django_ca/acme/todo/revoke-cert',
            'newAccount': req.build_absolute_uri('/django_ca/acme/%s/new-account/' % ca.serial),
            'newNonce': req.build_absolute_uri('/django_ca/acme/%s/new-nonce/' % ca.serial),
            'newOrder': req.build_absolute_uri('/django_ca/acme/%s/new-order/' % ca.serial),
            'meta': {
                "termsOfService": "https://localhost:8000/django_ca/example.pdf",
                "website": "https://localhost:8000",
            }
        })

    def test_no_ca(self):
        """Test using default CA when **no** CA exists."""
        CertificateAuthority.objects.all().delete()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertEqual(response['Content-Type'], 'application/problem+json')
        self.assertEqual(response.json(), {
            'detail': 'No (usable) default CA configured.',
            'status': 404,
            'type': 'urn:ietf:params:acme:error:not-found',
        })

    @freeze_time(timestamps['everything_expired'])
    def test_expired_ca(self):
        """Test using default CA when all CAs are expired."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertEqual(response['Content-Type'], 'application/problem+json')
        self.assertEqual(response.json(), {
            'detail': 'No (usable) default CA configured.',
            'status': 404,
            'type': 'urn:ietf:params:acme:error:not-found',
        })

    @override_settings(CA_ENABLE_ACME=False)
    def test_disabled(self):
        """Test that CA_ENABLE_ACME=False means HTTP 404."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)

    def test_unknown_serial(self):
        """Test explicitly naming an unknown serial."""
        serial = 'AB:CD:EF'
        url = reverse('django_ca:acme-directory', kwargs={'serial': serial})
        response = self.client.get(url)

        self.assertEqual(response['Content-Type'], 'application/problem+json')
        self.assertEqual(response.json(), {
            'detail': 'AB:CD:EF: CA not found.',
            'status': 404,
            'type': 'urn:ietf:params:acme:error:not-found',
        })


class NewNonceTestCase(DjangoCAWithCATestCase):
    """Test getting a new ACME nonce."""

    def setUp(self):
        super().setUp()
        self.url = reverse('django_ca:acme-new-nonce', kwargs={'serial': self.cas['root'].serial})

    @override_settings(CA_ENABLE_ACME=False)
    def test_disabled(self):
        """Test that CA_ENABLE_ACME=False means HTTP 404."""
        response = self.client.head(self.url)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)

    def test_get_nonce(self):
        """Test that getting multiple nonces returns unique nonces."""

        nonces = []
        for _i in range(1, 5):
            response = self.client.head(self.url)
            self.assertEqual(response.status_code, HTTPStatus.OK)
            nonces.append(response['replay-nonce'])

        self.assertEqual(len(nonces), len(set(nonces)))

    def test_unknown_ca(self):
        """Test fetching a nonce for an unknown CA."""
        url = reverse('django_ca:acme-new-nonce', kwargs={'serial': 'AA:BB:CC'})
        response = self.client.head(url)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)

    @freeze_time(timestamps['everything_expired'])
    def test_expired_ca(self):
        """Test using default CA when all CAs are expired."""
        response = self.client.head(self.url)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)


class AcmeNewAccountTestCase(DjangoCAWithCATestCase):
    """Test creating a new account."""

    # A collection of requests that where collected by certbot
    req1 = {
        'protected': 'eyJhbGciOiAiUlMyNTYiLCAiandrIjogeyJuIjogIm5ZVW5DZUI4VXY4X2pmdDRTRUgxTlBJbENCUE1OQVMtUUc2Q0ZzMmliRWI2MUs1ZU1KaTVMZFd5Y2FzY1FDYUppaS10VnpnRzc5LVk3Yzk5ZzVJbFNjVWhZY0l6aVB1b3ZBaFMxZkFXYmU0VEZWcHlFWjk2TzNFOTRvY3dQakh5MVdXT3AzSnR0cC15R2IxTFI4OWJOaTNJQmNFODE5UGJrNHVIWHhmbWMxWXk2UXlzY2ZwallMMFBvOWJfdkM1cXJ0X2pzWXpORGxxQlltNnlBYkpYak1lRVdIODdQZVBYcE9RbXhLNmI1Mk1SakwzR1RPaTBOUm5uUTJYc2RSdERBeXNySFJvU1lYR1pkb0VTUFJiVDlpRzUwTVE1ejZnRUdMa1QzeDYxQTZuQTRMQWxOX2RwdkxtYndQNGwtVmp3VzVUTEZjaUdnSFRyLVA0MnZGc0FsdyIsICJlIjogIkFRQUIiLCAia3R5IjogIlJTQSJ9LCAibm9uY2UiOiAiZGhKVnFYSUpMYVhLLW9ERHUzNkIzQmtTN3pCZzM5OWxfZE0ybktIWUV4NCIsICJ1cmwiOiAiaHR0cDovL2xvY2FsaG9zdDo4MDAwL2RqYW5nb19jYS9hY21lLzNGMUU2RTlCMzk5NkIyNkI4MDcyRTRERDI1OTdFOEI0MEYzRkJDN0UvbmV3LWFjY291bnQvIn0',  # NOQA: E501
        'signature': 'ajCXb6mJ2xjILHIAM44RqgCSPdUSfInEMHzhUl0w3qIVObmyTJvTWQl1mhdub2l9gg8O70uhfD-9S0OkOSgF01e4x-sXFemCjR74Og7t8rhbjfu0JjWZtQLDUNcb2mYJUBAx9vux8ezuVzFogK2KRjkqL4riPA7gOXXWQw3hxMqkNEwMvs0VoYO2HYdX6gA3EDLzdawl4hCCw1mXdZ3gYvBNT2t0i7xV0p4G9-h8IWUNF4JlXSAgp_muxN7E7oqcJU48chmIOKZg8EqAS_L48ePqTLBBDbYqPcuQGRSZZ_cJfd6tv7EHsH4fmGXYljt2sImxt0gLoeYRooOhQ-XZ2g',  # NOQA: E501
        'payload': 'ewogICJjb250YWN0IjogWwogICAgIm1haWx0bzp1c2VyQGxvY2FsaG9zdCIKICBdLAogICJ0ZXJtc09mU2VydmljZUFncmVlZCI6IHRydWUsCiAgInJlc291cmNlIjogIm5ldy1yZWciCn0'  # NOQA: E501
    }
    nonce1 = 'dhJVqXIJLaXK-oDDu36B3BkS7zBg399l_dM2nKHYEx4'
    req2 = {
        'protected': 'eyJhbGciOiAiUlMyNTYiLCAiandrIjogeyJuIjogIjNwUXJ3YWQyemZiMDU4eEhCenRBOWR6c3RtdlFzZ2Njc1E1dUVRZjBVdXY4bUk3UGFXVHRvSmM4Nk9fVWp2V0R5T0ZXZWVyYUNzV0QyYVBzU09lLXRQRGMtcUNBWThQbHVWMXNGanFLMHBSbElkaWk4UWRSRDYyRmtsOXZULTRlQjI1Zm8yXzktRExEMnF5V3RScmJGSDA0RjNBa1ZFY3hWQURvU3AtaXJtWjJtOVpDOUFLTF9GeUl4Yy1ybm82MktwVUhVWW82M3NpaUhPRVBubHlTb2IzcnZGeUROa1JsZ2JKQTYwLXNVQmYwMDJ3cTVsczhzVVVfazhyZTl4TnVIVW1XZGZWNW5QZEVzaU5fWXV5RlYtQzA2dEswTTVtMm1mbU9TN1c1RS1hMno3bkZxTlBIZUpTQUZJZk13bVJlSE9CZGtuem0yOXN3YnBTNGV6eVFMUSIsICJlIjogIkFRQUIiLCAia3R5IjogIlJTQSJ9LCAibm9uY2UiOiAiSGxYaEhzSlRwdmctRjhJVjNzSU81UjFIdzNPN2RMVDk3UEhkejN5UnRDRSIsICJ1cmwiOiAiaHR0cDovL2xvY2FsaG9zdDo4MDAwL2RqYW5nb19jYS9hY21lLzNGMUU2RTlCMzk5NkIyNkI4MDcyRTRERDI1OTdFOEI0MEYzRkJDN0UvbmV3LWFjY291bnQvIn0',  # NOQA: E501
        'signature': 'NPn-xMBHdfstuH7DNINWx7sdKy6VqgGHU3a8TY0aM_d8o-WWbDEhqsDbGgbMPqDsIyPuHVFPV30uCQW-R_AGvD6Px-qCn7beDjLJXsvSneD7zW20Cl_ceL_u3HyWZAWN1T6VKbMFvR9rL8KOawf6Pq6yVXEv2aiiSLQIj-wZXzcEMMtGzEnXudMcqfDw04Pv7ZEEzdg7b12juc504LoBWXoE7auZkeG-7e3ljApHxrzDxCeVqA3qJUmZJIVAf5YTdxVRCCMCzmtjrLtzyIDKWkXJSxz_p-W7r2Mx-sV0iJj1cr_RPDTAo4cGr3ycOW4e6B0HSlClorK9PTwI__f0aA',  # NOQA: E501
        'payload': 'ewogICJjb250YWN0IjogWwogICAgIm1haWx0bzp1c2VyQGxvY2FsaG9zdCIKICBdLAogICJ0ZXJtc09mU2VydmljZUFncmVlZCI6IHRydWUsCiAgInJlc291cmNlIjogIm5ldy1yZWciCn0'  # NOQA: E501
    }
    nonce2 = 'HlXhHsJTpvg-F8IV3sIO5R1Hw3O7dLT97PHdz3yRtCE'

    req3 = {
        'protected': 'eyJhbGciOiAiUlMyNTYiLCAiandrIjogeyJuIjogInczcTBmT3JTekNEbVZWd0daNkhpMTBQVXpqNTB6TlNLMWN5Szl3andxOExZMUlLUG1xS0RQM3AtQkQza28xclB1OVR4XzJHbGNnem50c0V1cGhrWHNFOHNzTGVzTjNnTjNMbVIzUVVNSzFYOUVvcFlPaXNTSGZIdkdGSnRXS2htYXVXdzBLY1JsMGJUd3pMdVZxbVBJTy1Fdl9wamdvWnhELWpZemlqUS1wa1dtYjBkNURCWTRtdGFRb0NFM0xud3Zsanl0aXA3bng1OGZoLUQ3VHVLazcxT3A1WnZEZnlld0Uwb2ljWnpBSjFjakNrQk1HVVB4UEpPLVlnUUdXdGtFbGRRS2M3S1hacEVlOTF3YTlwRllOSU5aTVdsMk1mVk5MUUtSd1BvY3R2c2tqQjc5WXVDX2ZCVXdoZDBBbktMWDdKSzIzU3BydTBvYnpHVWNkUEV4USIsICJlIjogIkFRQUIiLCAia3R5IjogIlJTQSJ9LCAibm9uY2UiOiAiQ3hBZGxxaC1mcHJ3WEhWNWVRQ3ZCQUhDQ05sdWhNMEpZRk1raFNuZnk2YyIsICJ1cmwiOiAiaHR0cDovL2xvY2FsaG9zdDo4MDAwL2RqYW5nb19jYS9hY21lLzNGMUU2RTlCMzk5NkIyNkI4MDcyRTRERDI1OTdFOEI0MEYzRkJDN0UvbmV3LWFjY291bnQvIn0',  # NOQA: E501
        'signature': 'DVhEztx6-M6hgwSmgrM-1jzzIxiD2SrBnwmPq2KIP3Cw2rAJC46g9Wtn6VuN371EtJR0TIdJ8dXrOZbR-Q63YdDvb6Kni9KxE0yIz0wOn5CvN6qdLIo6cndMF9sr4IiewV2BrI66MfExyxgojpVj9zQ7hWOaeXYKAb9UmUfRHE6Y7GdXoH7vcl2H0gEKXf30VT3t3i8GNA0sI4yk8i48BVEXLTqKP7RcFozkI_QDyKQOGH0zRkk8mZwZf110w9ztm8hWeyJ5nrYZNA_MJdOgzGUtsc4lF1Mw7ZtLc1EDzHvcFA4w-rBsS9LYxvvFFtJeT9UcQpQcs22UiufH05QCrg',  # NOQA: E501
        'payload': 'ewogICJjb250YWN0IjogWwogICAgIm1haWx0bzp1c2VyQGxvY2FsaG9zdCIKICBdLAogICJ0ZXJtc09mU2VydmljZUFncmVlZCI6IHRydWUsCiAgInJlc291cmNlIjogIm5ldy1yZWciCn0'  # NOQA: E501
    }
    nonce3 = 'CxAdlqh-fprwXHV5eQCvBAHCCNluhM0JYFMkhSnfy6c'

    def setUp(self):
        super().setUp()
        self.ca = self.cas['root']

    def get_nonce(self, ca=None):
        """Get a nonce with an actualy request."""
        if ca is None:
            ca = self.cas['root']

        url = reverse('django_ca:acme-new-nonce', kwargs={'serial': ca.serial})
        response = self.client.head(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        return response['replay-nonce']

    def post(self, url, data, **kwargs):
        """Make a post request with some ACME specific default data."""
        kwargs.setdefault('content_type', 'application/jose+json')
        kwargs.setdefault('SERVER_NAME', 'localhost:8000')
        return self.client.post(url, json.dumps(data), **kwargs)

    @override_settings(ALLOWED_HOSTS=['localhost'])
    @freeze_time(datetime(2020, 10, 29, 20, 15, 35))  # when we recorded these requests
    def test_precreated_requests(self):
        """Test requests collected by certbot."""

        self.ca.serial = '3F1E6E9B3996B26B8072E4DD2597E8B40F3FBC7E'
        self.ca.save()
        url = reverse('django_ca:acme-new-account', kwargs={'serial': self.ca.serial})

        for data, nonce in [(self.req1, self.nonce1), (self.req2, self.nonce2), (self.req3, self.nonce3)]:
            cache.set('acme-nonce-%s-%s' % (self.ca.pk, nonce), 0)
            response = self.post(url, data)
            self.assertEqual(response.status_code, HTTPStatus.CREATED)
            # TODO: validate other request properties