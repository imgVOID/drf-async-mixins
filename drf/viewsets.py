import asyncio
import inspect
import drf.mixins as mixins
from rest_framework.viewsets import ViewSetMixin as DRFViewSetMixin
from rest_framework.generics import GenericAPIView
from django.utils.decorators import classonlymethod
from django.utils.functional import classproperty
from functools import update_wrapper
from views import APIView
from utils import getmembers


class ViewSetMixin(DRFViewSetMixin):
    """
    This is the magic.

    Overrides `.as_view()` so that it takes an `actions` keyword that performs
    the binding of HTTP methods to actions on the Resource.

    For example, to create a concrete view binding the 'GET' and 'POST' methods
    to the 'alist' and 'acreate' actions...

    view = MyViewSet.as_view({'get': 'alist', 'post': 'acreate'})
    """

    @classonlymethod
    def as_view(cls, actions=None, **initkwargs):
        """
        Because of the way class based views create a closure around the
        instantiated view, we need to totally reimplement `.as_view`,
        and slightly modify the view function that is created and returned.
        """
        cls.name = None
        cls.description = None
        cls.suffix = None
        cls.detail = None
        cls.basename = None
        if not actions:
            raise TypeError(
                "The `actions` argument must be provided when "
                "calling `.as_view()` on a ViewSet. For example "
                "`.as_view({'get': 'list'})`"
            )
        for key in initkwargs:
            if key in cls.http_method_names:
                raise TypeError(
                    "You tried to pass in the %s method name as a "
                    "keyword argument to %s(). Don't do that." % (key, cls.__name__)
                )
            if not hasattr(cls, key):
                raise TypeError(
                    "%s() received an invalid keyword %r" % (cls.__name__, key)
                )
        if "name" in initkwargs and "suffix" in initkwargs:
            raise TypeError(
                "%s() received both `name` and `suffix`, which are "
                "mutually exclusive arguments." % (cls.__name__)
            )

        def view(request, *args, **kwargs):
            self = cls(**initkwargs)
            if "get" in actions and "head" not in actions:
                actions["head"] = actions["get"]
            self.action_map = actions
            for method, action in actions.items():
                handler = getattr(self, action)
                setattr(self, method, handler)
            self.request = request
            self.args = args
            self.kwargs = kwargs
            return self.dispatch(request, *args, **kwargs)

        async def async_view(request, *args, **kwargs):
            self = cls(**initkwargs)
            if "get" in actions and "head" not in actions:
                actions["head"] = actions["get"]
            self.action_map = actions
            for method, action in actions.items():
                handler = getattr(self, action)
                setattr(self, method, handler)
            self.request = request
            self.args = args
            self.kwargs = kwargs
            return await self.dispatch(request, *args, **kwargs)

        view = async_view if cls.view_is_async else view
        update_wrapper(view, cls, updated=())
        update_wrapper(view, cls.dispatch, assigned=())
        view.cls = cls
        view.initkwargs = initkwargs
        view.actions = actions
        view.csrf_exempt = True
        return view


class ViewSet(ViewSetMixin, APIView):
    _ASYNC_NON_DISPATCH_METHODS = [
        "check_async_object_permissions",
        "async_dispatch",
        "check_async_permissions",
        "check_async_throttles",
    ]

    @classproperty
    def view_is_async(cls):
        """
        Checks whether any viewset methods are coroutines.
        """
        return any(
            asyncio.iscoroutinefunction(function)
            for name, function in getmembers(
                cls, inspect.iscoroutinefunction, exclude_names=["view_is_async"]
            )
            if not name.startswith("__") and name not in cls._ASYNC_NON_DISPATCH_METHODS
        )


class GenericViewSet(ViewSet, GenericAPIView):
    _ASYNC_NON_DISPATCH_METHODS = ViewSet._ASYNC_NON_DISPATCH_METHODS


class ReadOnlyModelViewSet(
    mixins.RetrieveModelMixin, mixins.ListModelMixin, GenericViewSet
):
    """
    A viewset that provides default asynchronous `list()` and `retrieve()` actions.
    """

    pass


class ModelViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """
    A viewset that provides default asynchronous `create()`, `retrieve()`, `update()`,
    `partial_update()`, `destroy()` and `list()` actions.
    """

    pass
