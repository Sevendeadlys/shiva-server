# -*- coding: utf-8 -*-
from flask import json
from nose import tools as nose

from tests.integration.resource import ResourceTestCase


class ArtistResourceTestCase(ResourceTestCase):
    """
    GET /artists
        200 OK
        401 Unauthorized
    POST /artists name=<str> [image_url=<str>]
        201 Created
        400 Bad Request
        401 Unauthorized
        409 Conflict
    GET /artists/<id> [fulltree=<bool>]
        200 OK
        401 Unauthorized
        404 Not Found
    PUT /artists/<id> [name=<str>] [image_url=<str>]
        204 No Content
        400 Bad Request
        401 Unauthorized
        404 Not Found
    DELETE /artists/<id>
        204 No Content
        401 Unauthorized
        404 Not Found
    """

    def get_payload(self):
        return {
            'name': 'Flip',
        }

    def test_artist_base_resource(self):
        rv = self.app.get('/artists')
        resp = json.loads(rv.data)

        nose.eq_(rv.status_code, 200)
        nose.ok_(resp.has_key('item_count'))
        nose.ok_(resp.has_key('items'))
        nose.ok_(resp.has_key('page'))
        nose.ok_(resp.has_key('page_size'))
        nose.ok_(resp.has_key('pages'))

    def test_nonexistent_artist(self):
        rv = self.app.get('/artists/123')
        nose.eq_(rv.status_code, 404)

    def test_fulltree(self):
        rv = self.app.get('/artists/%s?fulltree=1' % self.album.pk)
        nose.eq_(rv.status_code, 200)

    def test_artist_creation(self):
        rv = self.app.post('/artists', data=self.get_payload())
        resp = json.loads(rv.data)

        nose.eq_(rv.status_code, 201)

        _rv = self.app.post('/artists', data=self.get_payload())
        nose.eq_(_rv.status_code, 409)  # Conflict

    def test_artist_update(self):
        url = '/artists/%s' % self.artist.pk
        old_name = self.artist.name

        rv = self.app.put(url, data={'name': '1on4'})
        rv = self.app.get(url)
        resp = json.loads(rv.data)

        nose.ok_(resp['name'] != old_name)

    def test_artist_deletion(self):
        rv = self.app.delete('/artists/%i' % self.artist.pk)
        nose.eq_(rv.status_code, 200)

        rv = self.app.get('/artists/%i' % self.artist.pk)
        nose.eq_(rv.status_code, 404)
