# -*- coding: utf-8 -*-
from datetime import datetime
import bcrypt
import hashlib
import os

from flask import current_app as app
from flask.ext.sqlalchemy import SQLAlchemy
from itsdangerous import (BadSignature, SignatureExpired,
                          TimedJSONWebSignatureSerializer as Serializer)
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.expression import func

from shiva.utils import slugify, MetadataManager

db = SQLAlchemy()

__all__ = ('db', 'Artist', 'Album', 'Track', 'LyricsCache', 'User')


def random_row(model):
    """Retrieves a random row for the given model."""

    try:
        # PostgreSQL, SQLite
        instance = model.query.order_by(func.random()).limit(1).first()
    except OperationalError:
        # MySQL
        instance = model.query.order_by(func.rand()).limit(1).first()

    return instance


# Table relationships
track_artist = db.Table('trackartist',
    db.Column('track_pk', db.Integer, db.ForeignKey('tracks.pk')),
    db.Column('artist_pk', db.Integer, db.ForeignKey('artists.pk')),
)

track_album = db.Table('trackalbum',
    db.Column('track_pk', db.Integer, db.ForeignKey('tracks.pk')),
    db.Column('album_pk', db.Integer, db.ForeignKey('albums.pk')),
)


class Artist(db.Model):
    __tablename__ = 'artists'

    pk = db.Column(db.Integer, primary_key=True)
    # TODO: Update the files' Metadata when changing this info.
    name = db.Column(db.String(128), unique=True, nullable=False)
    slug = db.Column(db.String(128), nullable=False)
    image = db.Column(db.String(256))
    events = db.Column(db.String(256))
    date_added = db.Column(db.Date(), nullable=False)

    def __init__(self, *args, **kwargs):
        if 'date_added' not in kwargs:
            kwargs['date_added'] = datetime.today()

        super(Artist, self).__init__(*args, **kwargs)

    @property
    def albums(self):
        # FIXME: Optimize. Check comments for Album.artists method.
        albums = []

        for track in self.tracks:
            for album in track.albums:
                if album not in albums:
                    albums.append(album)

        return albums

    @classmethod
    def random(cls):
        return random_row(cls)

    def __setattr__(self, attr, value):
        if attr == 'name':
            super(Artist, self).__setattr__('slug', slugify(value))

        super(Artist, self).__setattr__(attr, value)

    def __repr__(self):
        return '<Artist (%s)>' % self.name


class Album(db.Model):
    __tablename__ = 'albums'

    pk = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    slug = db.Column(db.String(128), nullable=False)
    year = db.Column(db.Integer)
    cover = db.Column(db.String(256))
    date_added = db.Column(db.Date(), nullable=False)

    def __init__(self, *args, **kwargs):
        if 'date_added' not in kwargs:
            kwargs['date_added'] = datetime.today()

        super(Album, self).__init__(*args, **kwargs)

    @property
    def artists(self):
        """
        Calculates the artists for this album by traversing the list of tracks.
        This is a terrible way of doing this, but we assume that the worst case
        will still be good enough to defer the optimization of this method for
        the future.
        """

        artists = []

        # FIXME: Optimize
        for track in self.tracks:
            for artist in track.artists:
                if artist not in artists:
                    artists.append(artist)

        return artists

    @classmethod
    def random(cls):
        return random_row(cls)

    def __setattr__(self, attr, value):
        if attr == 'name':
            super(Album, self).__setattr__('slug', slugify(value))

        super(Album, self).__setattr__(attr, value)

    def __repr__(self):
        return '<Album (%s)>' % self.name


class Track(db.Model):
    __tablename__ = 'tracks'

    pk = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.Unicode(256), unique=True, nullable=False)
    title = db.Column(db.String(128))
    slug = db.Column(db.String(128))
    bitrate = db.Column(db.Integer)
    file_size = db.Column(db.Integer)
    length = db.Column(db.Integer)
    ordinal = db.Column(db.Integer)
    date_added = db.Column(db.Date(), nullable=False)
    hash = db.Column(db.String(32))

    lyrics = db.relationship('LyricsCache', backref='tracks', uselist=False)
    albums = db.relationship('Album', secondary=track_album, lazy='dynamic',
                             backref=db.backref('tracks', lazy='dynamic'))
    artists = db.relationship('Artist', secondary=track_artist, lazy='dynamic',
                              backref=db.backref('tracks', lazy='dynamic'))

    def __init__(self, path, *args, **kwargs):
        if not isinstance(path, (basestring, file)):
            raise ValueError('Invalid parameter for Track. Path or File '
                             'expected, got %s' % type(path))

        _path = path
        if isinstance(path, file):
            _path = path.name

        no_metadata = kwargs.get('no_metadata', False)
        if 'no_metadata' in kwargs:
            del(kwargs['no_metadata'])

        hash_file = kwargs.get('hash_file', False)
        if 'hash_file' in kwargs:
            del(kwargs['hash_file'])

        self._meta = None
        self.set_path(_path, no_metadata=no_metadata)
        if hash_file:
            self.hash = self.calculate_hash()

        if 'date_added' not in kwargs:
            kwargs['date_added'] = datetime.today()

        super(Track, self).__init__(*args, **kwargs)

    @classmethod
    def random(cls):
        return random_row(cls)

    def __setattr__(self, attr, value):
        if attr == 'title':
            super(Track, self).__setattr__('slug', slugify(value))

        super(Track, self).__setattr__(attr, value)

    def get_path(self):
        if self.path:
            return self.path.encode('utf-8')

        return None

    def set_path(self, path, no_metadata=False):
        if path != self.get_path():
            self.path = path
            if no_metadata:
                return None

            if os.path.exists(self.get_path()):
                meta = self.get_metadata_reader()
                self.file_size = meta.filesize
                self.bitrate = meta.bitrate
                self.length = meta.length
                self.ordinal = meta.track_number
                self.title = meta.title

    def calculate_hash(self):
        md5 = hashlib.md5()
        block_size = 128 * md5.block_size

        with open(self.get_path(), 'rb') as f:
            for chunk in iter(lambda: f.read(block_size), b''):
                md5.update(chunk)

        return md5.hexdigest()

    def get_metadata_reader(self):
        """Return a MetadataManager object."""
        if not getattr(self, '_meta', None):
            self._meta = MetadataManager(self.get_path())

        return self._meta

    def __repr__(self):
        return "<Track ('%s')>" % self.title


class LyricsCache(db.Model):
    __tablename__ = 'lyricscache'

    pk = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text)
    source = db.Column(db.String(256))

    track_pk = db.Column(db.Integer, db.ForeignKey('tracks.pk'),
                         nullable=False)

    def __repr__(self):
        return "<LyricsCache ('%s')>" % self.track.title


class User(db.Model):
    __tablename__ = 'users'

    pk = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(256))
    email = db.Column(db.String(256), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=True)
    salt = db.Column(db.String(256), nullable=True)

    # Metadata
    # Should these attributes be in their own table?
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    creation_date = db.Column(db.DateTime, nullable=False)

    def __init__(self, *args, **kwargs):
        kwargs['creation_date'] = datetime.now()

        super(User, self).__init__(*args, **kwargs)

    def __setattr__(self, *args, **kwargs):
        if args[0] == 'password':
            password = args[1]
            salt = None

            if password not in (None, ''):
                password, salt = self.hash_password(password)

            self.salt = salt
            args = ('password', password)

        super(User, self).__setattr__(*args, **kwargs)

    def hash_password(self, password, salt=None):
        salt = salt or self.salt or bcrypt.gensalt()
        _pass = bcrypt.hashpw(password.encode('utf-8'), salt.encode('utf-8'))

        return (_pass, salt)

    def verify_password(self, password):
        _password, salt = self.hash_password(password)

        return _password == self.password

    def generate_auth_token(self, expiration=None):
        if not expiration:
            expiration = app.config.get('AUTH_EXPIRATION_TIME', 3600)

        if not isinstance(expiration, int):
            raise ValueError

        s = Serializer(app.config['SECRET_KEY'], expires_in=expiration)

        return s.dumps({'pk': self.pk})

    @staticmethod
    def verify_auth_token(token):
        s = Serializer(app.config['SECRET_KEY'])

        try:
            data = s.loads(token)
        except (SignatureExpired, BadSignature):
            return None

        user = User.query.get(data['pk'])

        return user

    def __repr__(self):
        return "<User ('%s')>" % self.email
