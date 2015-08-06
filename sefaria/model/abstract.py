"""
abstract.py - abstract classes for Sefaria models
"""
import collections
import logging
import copy

#Should we import "from abc import ABCMeta, abstractmethod" and make these explicity abstract?
#

from bson.objectid import ObjectId

from sefaria.system.database import db
from sefaria.system.exceptions import InputError

logging.basicConfig()
logger = logging.getLogger("abstract")
logger.setLevel(logging.WARNING)


class AbstractMongoRecord(object):
    """
    AbstractMongoRecord - superclass of classes representing mongo records.
    "collection" attribute is set on subclass
    """
    collection = None  # name of MongoDB collection
    id_field = "_id" # Mongo ID field
    criteria_field = "_id"  # Primary ID used to find existing records
    criteria_override_field = None # If a record type uses a different primary key (such as 'title' for Index records), and the presence of an override field in a save indicates that the primary attribute is changing ("oldTitle" in Index records) then this class attribute has that override field name used.
    required_attrs = []  # list of names of required attributes
    optional_attrs = []  # list of names of optional attributes
    track_pkeys = False
    pkeys = []   # list of fields that others may depend on
    history_noun = None  # Label for history records
    second_save = False  # Does this object need a two stage save?  Uses _prepare_second_save()

    def __init__(self, attrs=None):
        self._init_defaults()
        self.pkeys_orig_values = {}
        if attrs:
            self.load_from_dict(attrs, True)

    def load_by_id(self, _id=None):
        if _id is None:
            raise Exception(type(self).__name__ + ".load() expects an _id as an arguemnt. None provided.")

        if isinstance(_id, basestring):
            # allow _id as either string or ObjectId
            _id = ObjectId(_id)
        return self.load({"_id": _id})

    def load(self, query, proj=None):
        obj = getattr(db, self.collection).find_one(query, proj)
        if obj:
            assert set(obj.keys()) <= set(self._saveable_attr_keys()), \
                "{} record loaded with unhandled key(s): {}".format(
                    type(self).__name__,
                    set(obj.keys()) - set(self._saveable_attr_keys())
                )
            self.load_from_dict(obj, True)
            return self
        return None  # used to check for existence of record.

    # careful that this doesn't defeat itself, if/when a cache catches constructor calls
    def copy(self):
        attrs = self._saveable_attrs()
        del attrs[self.id_field]
        return self.__class__(copy.deepcopy(attrs))


    def load_from_dict(self, d, is_init=False):
        """
        Add values from a dict to an existing object.
        Used internally both to initialize new objects and to update existing objects

        :param dict d: The dictionary used to update the object
        :param bool is_init: Indicates whether this dictionary is initializing (as opposed to updating) an object.  If this is true, the primary keys are tracked from this load, and any change will trigger an 'attributeChange' notification.
        :return: the object
        """
        for key, value in d.items():
            setattr(self, key, value)
        if is_init and not self.is_new():
            self._set_pkeys()
        self._set_derived_attributes()
        return self

    def update(self, query, attrs):
        """
        :param query: Query to find existing object to update.
        :param attrs: Dictionary of attributes to update.
        :return: the object
        """
        if not self.load(query):
            raise InputError("No existing {} record found to update for {}".format(type(self).__name__, str(query)))
        self.load_from_dict(attrs)
        return self.save()

    def save(self):
        """
        Save the object to the Mongo data store.
        On completion, will emit a 'save' notification.  If a tracked attribute has changed, will emit an 'attributeChange' notification.
        :return: the object
        """
        is_new_obj = self.is_new()

        self._normalize()
        self._validate()
        self._pre_save()

        props = self._saveable_attrs()

        if self.track_pkeys and not is_new_obj:
            if not (len(self.pkeys_orig_values) == len(self.pkeys)):
                raise Exception("Aborted unsafe {} save. {} not fully tracked.".format(type(self).__name__, self.pkeys))

        _id = getattr(db, self.collection).save(props, w=1)

        if is_new_obj:
            self._id = _id

        if self.second_save:
            self._prepare_second_save()
            getattr(db, self.collection).save(props, w=1)

        # Not sure about the order of these notifications firing.
        if self.track_pkeys and not is_new_obj:
            for key, old_value in self.pkeys_orig_values.items():
                if old_value != getattr(self, key):
                    notify(self, "attributeChange", attr=key, old=old_value, new=getattr(self, key))

        ''' Not yet used
        self._post_save()
        '''

        notify(self, "save", orig_vals=self.pkeys_orig_values)
        if is_new_obj:
            notify(self, "create")

        #Set new values as pkey_orig_values so that future changes will be caught
        if self.track_pkeys:
            for pkey in self.pkeys:
                self.pkeys_orig_values[pkey] = getattr(self, pkey, None)

        return self

    def delete(self):
        if self.is_new():
            raise InputError("Can not delete {} that doesn't exist in database.".format(type(self).__name__))

        #if self.track_pkeys:
        #    for pkey in self.pkeys:
        #        self.pkeys_orig_values[pkey] = getattr(self, pkey)

        getattr(db, self.collection).remove({"_id": self._id})
        notify(self, "delete")

        #if self.track_pkeys:
        #    for key, old_value in self.pkeys_orig_values.items():
        #        notify(self, "attributeChange", attr=key, old=old_value, new=None)

    def delete_by_query(self, query):
        r = self.load(query)
        if r:
            r.delete()

    def is_new(self):
        return getattr(self, "_id", None) is None

    def _saveable_attr_keys(self):
        return self.required_attrs + self.optional_attrs + [self.id_field]

    def _saveable_attrs(self):
        return {k: getattr(self, k) for k in self._saveable_attr_keys() if hasattr(self, k)}

    def contents(self, **kwargs):
        """ Build a savable/portable dictionary from the object
        Extended by subclasses with derived attributes passed along with portable object
        :return: dict
        """
        d = self._saveable_attrs()
        del d[self.id_field]
        return d

    def _set_pkeys(self):
        if self.track_pkeys:
            for pkey in self.pkeys:
                self.pkeys_orig_values[pkey] = getattr(self, pkey, None)

    def _init_defaults(self):
        pass

    def _set_derived_attributes(self):
        pass

    def _validate(self):
        """
        Test self for validity
        :return: True on success
        Throws Exception on failure
        """

        attrs = vars(self)

        """" This fails when the object has been created but not yet saved.
        if not getattr(self, self.id_field, None):
            logger.debug(type(self).__name__ + ".is_valid: No id field " + self.id_field + " found.")
            return False
        """

        for attr in self.required_attrs:
            #properties. which are virtual instance members, do not get returned by vars()
            if attr not in attrs and not getattr(self, attr, None):
                raise InputError(type(self).__name__ + "._validate(): Required attribute: " + attr + " not in " + ", ".join(attrs))

        """ This check seems like a good idea, but stumbles as soon as we have internal attrs
        for attr in attrs:
            if attr not in self.required_attrs and attr not in self.optional_attrs and attr != self.id_field:
                logger.debug(type(self).__name__ + ".is_valid: Provided attribute: " + attr +
                             " not in " + ",".join(self.required_attrs) + " or " + ",".join(self.optional_attrs))
                return False
        """
        return True

    def _normalize(self):
        pass

    def _prepare_second_save(self):
        pass

    def _pre_save(self):
        pass

    ''' Not yet used.
    def _post_save(self, *args, **kwargs):
        pass
    '''

    def same_record(self, other):
        if getattr(self, "_id", None) and getattr(other, "_id", None):
            return ObjectId(self._id) == ObjectId(other._id)
        return False

    def __eq__(self, other):
        """

        """
        if type(other) is type(self):
            return self._saveable_attrs() == other._saveable_attrs()
        return False

    def __ne__(self, other):
        return not self.__eq__(other)


class AbstractMongoSet(collections.Iterable):
    """
    A set of mongo records from a single collection
    """
    recordClass = AbstractMongoRecord

    def __init__(self, query={}, page=0, limit=0, sort=[["_id", 1]], proj=None):
        self.raw_records = getattr(db, self.recordClass.collection).find(query, proj).sort(sort).skip(page * limit).limit(limit)
        self.has_more = limit != 0 and self.raw_records.count() == limit
        self.records = None
        self.current = 0
        self.max = None
        self._local_iter = None

    def __iter__(self):
        self._read_records()
        return iter(self.records)

    def __getitem__(self, item):
        self._read_records()
        return self.records[item]

    def _read_records(self):
        if self.records is None:
            self.records = []
            for rec in self.raw_records:
                self.records.append(self.recordClass(attrs=rec))
            self.max = len(self.records)

    def __len__(self):
        if self.max:
            return self.max
        else:
            return self.raw_records.count()

    def array(self):
        self._read_records()
        return self.records

    def distinct(self, field):
        return self.raw_records.distinct(field)

    def count(self):
        return len(self)

    def update(self, attrs):
        for rec in self:
            rec.load_from_dict(attrs).save()

    def delete(self):
        for rec in self:
            rec.delete()

    def save(self):
        for rec in self:
            rec.save()


def get_subclasses(c):
    subclasses = c.__subclasses__()
    for d in list(subclasses):
        subclasses.extend(get_subclasses(d))

    return subclasses


def get_record_classes(concrete=True):
    sc = get_subclasses(AbstractMongoRecord)
    if concrete:
        return [s for s in sc if s.collection is not None]
    else:
        return sc


def get_set_classes():
    return get_subclasses(AbstractMongoSet)


"""
    Metaclass to provides a caching mechanism for objects of classes using this metaclass.
    Based on: http://chimera.labs.oreilly.com/books/1230000000393/ch09.html#metacreational

    Not yet used
"""


class CachingType(type):

    def __init__(cls, name, parents, dct):
        super(CachingType, cls).__init__(name, parents, dct)
        cls.__cache = {}

    def __call__(cls, *args, **kwargs):
        key = make_hashable(args), make_hashable(kwargs)
        if key in cls.__cache:
            return cls.__cache[key]
        else:
            obj = super(CachingType, cls).__call__(*args)
            cls.__cache[key] = obj
            return obj


def make_hashable(obj):
    """WARNING: This function only works on a limited subset of objects
    Make a range of objects hashable.
    Accepts embedded dictionaries, lists or tuples (including namedtuples)"""
    if isinstance(obj, collections.Hashable):
        #Fine to be hashed without any changes
        return obj
    elif isinstance(obj, collections.Mapping):
        #Convert into a frozenset instead
        items = list(obj.items())
        for i, item in enumerate(items):
            items[i] = make_hashable(item)
        return frozenset(items)
    elif isinstance(obj, collections.Iterable):
        #Convert into a tuple instead
        ret=[type(obj)]
        for i, item in enumerate(obj):
            ret.append(make_hashable(item))
        return tuple(ret)
    #Use the id of the object
    return id(obj)


"""
Register for model dependencies.
If instances of Model X depend on field f in Model Class Y:
- X subscribes with: subscribe(Y, "f", X.callback)
- On a chance of an instance of f, Y calls: notify(Y, "f", old_value, new_value)

todo: currently doesn't respect any inheritance
todo: find a way to test that dependencies have been regsitered correctly


>>> from sefaria.model import *
>>> def handle(old, new):
...     print "Old : " + old
...     print "New : " + new
...
>>> subscribe(index.Index, "title", handle)
>>> notify(index.Index(), "title", "yellow", "green")
Old : yellow
New : green
"""

deps = {}


def notify(inst, action, **kwargs):
    """
    :param inst: An object instance
    :param action: Currently used: "save", "attributeChange", "delete", "create", ... could also be "change"
    """

    actions_reqs = {
        "attributeChange": ["attr", "old", "new"],
        "save": [],
        "delete": [],
        "create": []
    }
    assert inst
    assert action in actions_reqs.keys()

    for arg in actions_reqs[action]:
        if not kwargs.get(arg, None):
            raise Exception("Missing required argument {} in notify {}, {}".format(arg, inst, action))

    if action == "attributeChange":
        callbacks = deps.get((type(inst), action, kwargs["attr"]), None)
        logger.debug("Notify: " + str(inst) + "." + kwargs["attr"] + ": " + kwargs["old"] + " is becoming " + kwargs["new"])
    else:
        logger.debug("Notify: " + str(inst) + " is being " + action + "d.")
        callbacks = deps.get((type(inst), action, None), [])

    for callback in callbacks:
        logger.debug("Notify: Calling " + callback.__name__ + "() for " + inst.__class__.__name__ + " " + action)
        callback(inst, **kwargs)


def subscribe(callback, klass, action, attr=None):
    if not deps.get((klass, action, attr), None):
        deps[(klass, action, attr)] = []
    deps[(klass, action, attr)].append(callback)


def cascade(set_class, attr):
    """
    Handles generic value cascading, for simple key reference changes.
    See examples in dependencies.py
    :param set_class: The set class of the impacted model
    :param attr: The name of the impacted class attribute (fk) that holds the references to the changed attribute (pk)
    :return: a function that will update 'attr' in 'set_class' and can be passed to subscribe()
    """
    return lambda obj, kwargs: set_class({attr: kwargs["old"]}).update({attr: kwargs["new"]})
