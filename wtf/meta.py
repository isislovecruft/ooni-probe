#-*- coding: utf-8 -*-
#
# meta.py
# -------
# Meta classes for coercing subclasses which don't exist yet, including ways
# to automatically create subclasses with property attributes. This file also
# contains utilities for wrapping functions and creating subclasses which are
# semaphoric.
#
# :authors: Isis Lovecruft
# :version: 0.1.0-alpha
# :copyright: 2012 Isis Lovecruft
# :license: see attached LICENSE file
#

from twisted.internet import defer


class MetaDescriptor(type):
    """
    bug: "Attribute error: class <> has no attribute __bases__"

    There are only objects. However, there *are* two kinds of objects:
    type-objects and non-type-objects.

    There are only two objects which do not have an attribute named
    "__bases__":

        1) Instances of the builtin object ``object`` itself (i.e. the
           superclass of any top-level class in python), whose __class__ is
           itself, and whose type is ``type(type)``:

           >>> o = object()
           >>> type(o)
              <type 'type'>
           >>> o.__class__
              <type 'object'>

           The o.__class__ part seems to imply that the __bases__ of
           ``object`` should be itself.

        2) Old Style Classes. Which are despicable demons, deserving to be
           sent straight back to hell. No offense to the good Satanas. The
           only thing these have by default is __doc__ and __module__. Also,
           and this is importants too: Old Style Classes do not have an
           attribute named __class__, because they do not derive from
           anything.

    Incidentally, the type of ``type(type)`` is itself, and the "__bases__" of
    ``type(type)`` is...

    >>> t = type(type)
    >>> t.__name__
    'type'
    >>> type(t)
       <type 'type'>
    >>> t.__class__
       <type 'type'>
    >>> t.__bases__
       (<type 'object'>,)

    ``type(object)``. WTF. This is to say that the "__bases__" of ``object``
    is the ``type`` of itself. This strange loop is where all black magic
    enters into Python.

    If we do "class Metaclass(type): pass", we can then call
    ``super(Metaclass, mcls)``, and the resulting ``super`` object is actually
    just ``type``:

        o Its type is ``type(type)``.
        o Its __bases__ ``type(object)``.

    For example, ``super(Metaclass, mcls).__new__(mcls, *a, *kw)`` is the same
    as saying ``type(mcls, "Metaclass", (type, ), {} )``, except that super
    does some namespace munging with calling "self.__super" on its own type,
    which is probably equivalent to the strange loops with type(type) and
    type(object), but my brain is already flipping out (and I keep a string
    cosmology textbook on my nightstand!).

    However, we should not ever be able to call

    >>> super(type, type(mcls)).__new__(type(mcls), 'type', (type(type),) {} )
    TypeError: object.__new__(type) is not safe, use type.__new__()

    Q: Why all this fuss?

    A: We need to force future class-level attributes of subclasses of
       NetTestCase to be accessible (also at the class-level, without
       instatiations) by NetTestCase. I.e.:
           1) class SubNetTestCase has class attribute optParameters, but no
              class for doing anything with them, and they shouldn't have to.
              They should just be able to define the options.
           2) Therefore, NetTestCase needs to have data descriptors, which get
              inherited.
           3) We need to be able to do this without dangerous namespace
              munging, because we cannot control the namespace of future
              tests. Therefore, we cannot use hacks like "self.__super".

       We need a Metaclass, which creates a Metafactory for classes which are
       dynamic test descriptors. If this is confusing, leave it alone, there's
       witches is these woods.

    http://stackoverflow.com/a/10707719
    http://docs.python.org/2/howto/descriptor.html
    http://www.no-ack.org/2011/03/strange-behavior-with-properties-on.html
    http://www.cafepy.com/article/python_types_and_objects/
    http://stackoverflow.com/questions/100003/what-is-a-metaclass-in-python

    """
    ## DO NOT GIVE A METACLASS ATTRIBUTES HERE.
    #descriptors = { }

    from byteplay  import Code, opmap
    from functools import partial

    def __new__(im_so_meta_even_this_acronym, name, base, dict):

        def hofstaeder_decorator(meta_decorator):
            def meta_decorator_factory(*args, **kwargs):
                def meta_decorator_wrapper(func):
                    return meta_decorator(func, *args, **kwargs)
                return meta_decorator_wrapper
            return meta_decorator_factory

        def _transmute(opcode, arg):
            if ((opcode == opmap['LOAD_GLOBAL']) and
                (arg == 'self')):
                return opmap['LOAD_FAST'], arg
            return opcode, arg

        def selfless(child):
            code = Code.from_code(child.func_code)
            code.args = tuple(['self'] + list(code.args))
            code.code = [_transmute(op, arg) for op, arg in code.code]
            function.func_code = code.to_code()
            return function

        acronym = ( ( k,v ) for k,v in dict.items( )
                    if not k.startswith('__') )
        metanym, polymorph = ( (k for ( k,v ) in acronym),
                               (v for ( k,v ) in acronym) )
        morphonemes = (("get%s"%n, "set%s"%n, "del%s"%n) for n in metanym )

        oracles = []
        for getter, setter, deleter in morphonemes:
            childnym = getter[3:]

            @hofstaeder_decorator
            def meta_decorator(func, *args, **kwargs):
                def decorator_wrapper(first, last):
                    return func(first, last)
                return decorator_wrapper

            @meta_decorator(getter, setter, deleter)
            def decorated_property(first, last):
                childnym = getter[3:]
                class DataDescriptor(object):
                    @selfless
                    def __init__(childnym=None, polymorph):
                        setattr(self, childnym, polymorph)

                    @property
                    @selfless
                    def getter():
                        return self.childnym
                return DataDescriptor(first, last)

            oracles.append(decorated_property(childnym, polymorph))

        return super(
            MetaDescriptor, im_so_meta_even_this_acronym).__new__(
            im_so_meta_even_this_acronym,
            metanym,
            polymorph,
            dict(oracles) )
'''
    @property
    def x(self):        ## or getx
        return self._x
    @x.setter
    def x(self, value): ## or setx
        self._x = value
    @x.deleter
    def x(self):        ## or delx
        del self._x
    ## or 'x = property(getx, setx, delx, "documentation")'
    ##     ^               ^     ^     ^
    ## just need @property's name, initial value can be None

Metaclass
   Creates Metaclasses for each data descriptor in each SubNetTestCase
        so, per SubNetTestCase, we get (usually two) descriptors:
        optParameters and input

'''

def applyClassAttribute(obj, cls, get='optParameters'):
    """
    I get attributes from an outside instances' dictionary and attempt to
    apply them to a class. I require that the attributes I am trying to set be
    data descriptors which is just Python name munging trick that is mild and
    harmless enough to have it's own builtin decorator helper:

        class Foo(object):
            def __init__(self, *a, **kw):
                if 'thing' in kw:
                    self._thing = thing
            @property
            def thing(self):
                return self._thing
            @property.setter
            def thing(self, value):
                self._thing = value
            @property.delter
            def thing(self):
                return del(self)
    """
    from ooni.utils.assertions import isClass, isNotClass

    try:
        assert isNotClass(obj), "must be an instance"
        assert isClass(cls), "not a class"
                                        ## obj is probably an instance
        C = obj.__class__               ## of a subclass of nettest.NetTestCase

        assert issubclass(C, cls), "not a subclass of %s" % cls
        assert C.__dict__.__contains__('optParameters'), \
            "%s in %s.__dict__ not found" % (get, C)
    except AssertionError, ae:
        log.debug(ae)
    else:
        attributes = classify_class_attrs(C)
        ## uncomment this to have class attributes spewn everywhere:
        #log.debug("Found class attributes:\n%s" % pprint(attributes))
        for attr in attributes:
            if attr.name == str(get):
                setattr(obj, str(get), attr.object)
        if not hasattr(obj, str(get)):
            log.debug("Unable to find class attribute %s" % get)
        else:
            log.debug("Applying %s.%s = %s to descriptor..."
                      % (C.name, attr.name, attr.object))
        ## This was an unfinished attempt at fixing a class' __bases__, I do
        ## not know if it was heading in the right direction. It can be
        ## removed it is still crufting up the space. --isis
        if '__bases__' or '_parents' in C.__dict__:
            pass


@defer.inlineCallbacks
def singleton_semaphore(deferred_process_init,
                        callbacks=[], errbacks=[],
                        max_inits=1):
    """
    Initialize a process only once, and do not return until
    that initialization is complete. If the keyword parameter max_inits=
    is given, run the process a maximum of that number of times.

    :param deferred_process_init:
        A deferred which returns a connected process via
        :meth:`twisted.internet.reactor.spawnProcess`.
    :param callbacks:
        A list of callback functions to add to the initialized processes'
        deferred.
    :param errbacks:
        A list of errback functions to add to the initialized processes'
        deferred.
    :param max_inits:
        An integer specifying the maximum number of allowed
        initializations for :param:deferred_process_init. If no maximum
        is given, only one instance (a singleton) of the process is
        initialized.
    :return:
        The final state of the :param deferred_process_init: after the
        callback chain has completed. This should be a fully initialized
        process connected to a :class:`twisted.internet.reactor`.
    """
    assert isinstance(callbacks, list)
    assert isinstance(errbacks, list)
    assert isinstance(max_inits, int)

    for cb in callbacks:
        deferred_process_init.addCallback(cb)
    for eb in errbacks:
        deferred_process_init.addErrback(eb)

    only_this_many = defer.DeferredSemaphore(max_inits)
    singleton = yield only_this_many.run(deferred_process_init)
    defer.returnValue(singleton)

class Singleton(object):
    """
    Generic Class for creating Singleton subclasses.

    Subclass me to create a singleton class, which will only ever have one
    instance, regardless of how many times the subclass constructor is called.

    Any subclass of me should override ``init`` rather than ``__init__``,
    because the latter is called whenever the constructor is called.
    """
    def __new__(cls, *args, **kwds):
        it = cls.__dict__.get("__it__")
        if it is not None:
            return it
        cls.__it__ = it = object.__new__(cls)
        it.init(*args, **kwds)
        return it
    def init(self, *args, **kwds):
        pass
