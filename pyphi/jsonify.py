#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# jsonify.py

"""
PyPhi- and NumPy-aware JSON serialization.

To be properly serialized and deserialized, PyPhi models must implement a
``to_json`` method which returns a dictionary of attribute names and attribute
values. These attributes should be the names of arguments passed to the model
constructor. If the constructor takes additional, fewer, or differnt arguments,
the model needs to implement a custom ``from_json`` classmethod which takes a
Python dictionary as an argument and returns a PyPhi object. For example::

    class Phi:
        def __init__(self, phi):
            self.phi = phi

        def to_json(self):
            return {'phi': self.phi, 'twice_phi': 2 * self.phi}

        @classmethod
        def from_json(cls, json):
            return Phi(json['phi'])

The model must also be added to ``jsonify._loadable_models``.

The JSON encoder adds the name of the model and the current PyPhi version to
the JSON stream. The JSON decoder uses this metadata to recursively deserialize
the stream to a nested PyPhi model structure. The decoder will raise an
exception if the version of the JSON does not match the current version of
PyPhi.
"""

import json

import numpy as np

import pyphi

CLASS_KEY = '__class__'
VERSION_KEY = '__version__'


def _loadable_models():
    """A dictionary of loadable PyPhi models.

    These are stored in this function (instead of module scope) to resolve
    circular import issues.
    """
    classes = [
        pyphi.Network,
        pyphi.Subsystem,
        pyphi.models.Cut,
        pyphi.models.Part,
        pyphi.models.Bipartition,
        pyphi.models.Mip,
        pyphi.models.Mice,
        pyphi.models.Concept,
        pyphi.models.Constellation,
        pyphi.models.BigMip,
    ]
    return {cls.__name__: cls for cls in classes}


class JSONVersionError(ValueError):
    pass


def _jsonify_dict(dct):
    return {key: jsonify(value) for key, value in dct.items()}


def jsonify(obj):
    """Return a JSON-encodable representation of an object, recursively using
    any available ``to_json`` methods, converting NumPy arrays and datatypes to
    native lists and types along the way."""

    if hasattr(obj, 'to_json'):
        # Call the `to_json` method if available.
        d = obj.to_json()

        # Add metadata
        d[CLASS_KEY] = obj.__class__.__name__
        d[VERSION_KEY] = pyphi.__version__

        return jsonify(d)

    # If we have a numpy array, convert it to a list.
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    # If we have NumPy datatypes, convert them to native types.
    if isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    if isinstance(obj, np.float64):
        return float(obj)
    # Recurse over dictionaries.
    if isinstance(obj, dict):
        return _jsonify_dict(obj)
    # Recurse over object dictionaries.
    if hasattr(obj, '__dict__'):
        return _jsonify_dict(obj.__dict__)
    # Recurse over lists and tuples.
    if isinstance(obj, (list, tuple)):
        return [jsonify(item) for item in obj]
    # Otherwise, give up and hope it's serializable.
    return obj


class PyPhiJSONEncoder(json.JSONEncoder):

    """Extension of the default JSONEncoder that allows for serializing PyPhi
    objects with ``jsonify``."""

    def encode(self, obj):
        """Encode the output of ``jsonify`` with the default encoder."""
        return super().encode(jsonify(obj))

    def iterencode(self, obj, **kwargs):
        """Analog to `encode` used by json.dump."""
        return super().iterencode(jsonify(obj), **kwargs)


def _encoder_kwargs(user_kwargs):
    """Update kwargs for `dump` and `dumps` to use the PyPhi encoder."""
    kwargs = {'separators': (',', ':'), 'cls': PyPhiJSONEncoder}
    kwargs.update(user_kwargs)

    return kwargs


def dumps(obj, **user_kwargs):
    """Serialize ``obj`` as JSON-formatted stream."""
    return json.dumps(obj, **_encoder_kwargs(user_kwargs))


def dump(obj, fp, **user_kwargs):
    """Serialize ``obj`` as a JSON-formatted stream and write to ``fp`` (a
    ``.write()``-supporting file-like object."""
    return json.dump(obj, fp, **_encoder_kwargs(user_kwargs))


def _check_version(version):
    """Check whether the JSON version matches the PyPhi version."""
    if version != pyphi.__version__:
        raise JSONVersionError(
            'Cannot load JSON from a different version of PyPhi. '
            'JSON version = {0}, current version = {1}.'.format(
                version, pyphi.__version__))


class PyPhiJSONDecoder(json.JSONDecoder):
    """Extension of the default encoder which automatically deserializes
    PyPhi JSON to the appropriate model classes.
    """
    def __init__(self, *args, **kwargs):
        kwargs['object_hook'] = self._load_object
        super().__init__(*args, **kwargs)

        # Memoize available models
        self._loadable_models = _loadable_models()

    def _load_object(self, obj):
        """Recursively load a PyPhi object."""
        if isinstance(obj, dict):
            obj = {k: self._load_object(v) for k, v in obj.items()}

            # PyPhi class dictionary
            if CLASS_KEY in obj:
                cls = self._loadable_models[obj[CLASS_KEY]]

                _check_version(obj[VERSION_KEY])

                del obj[CLASS_KEY], obj[VERSION_KEY]

                # If implemented, use the `from_json` method
                if hasattr(cls, 'from_json'):
                    return cls.from_json(obj)

                # Otherwise pass the dictionary as keyword arguments
                return cls(**obj)

        # Cast to tuple because most iterables in PyPhi are ultimately tuples
        # (eg. mechanisms, purviews.) Other iterables (tpms, repertoires)
        # should be cast to the correct type in init methods
        if isinstance(obj, list):
            return tuple(self._load_object(item) for item in obj)

        return obj


def loads(string):
    """Deserialize a JSON string to a Python object."""
    return json.loads(string, cls=PyPhiJSONDecoder)


def load(fp):
    """Deserialize a JSON stream to a Python object."""
    return json.load(fp, cls=PyPhiJSONDecoder)
