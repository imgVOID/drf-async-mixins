from hashlib import md5
from asgiref.sync import sync_to_async
from adrf import mixins
from adrf.viewsets import GenericViewSet
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response


async def generate_cache_key(view):
    model_name = view.get_serializer_class()
    return md5(model_name.Meta.model.__name__.lower().encode()).hexdigest()


async def generate_request_cache_key(request):
    return md5(request.get_full_path().encode()).hexdigest()


async def get_data(serializer):
    try:
        data = await serializer.adata
    except Exception:
        data = await sync_to_async(getattr)(serializer, 'data')
    return data


class ListModelMixin(mixins.ListModelMixin):
    async def alist(self, request, *args, **kwargs):
        cache_key_page = await generate_request_cache_key(request)
        cache_key = await generate_cache_key(self)
        if not await cache.ahas_key(cache_key_page):
            queryset = self.filter_queryset(self.get_queryset())
            page = await self.apaginate_queryset(queryset)
            serializer = self.get_serializer(queryset if page is None else page, many=True)
            id_name = getattr(serializer.__class__, "custom_id", "id")
            data = await get_data(serializer)
            data_ids, cached_data = [], {}
            for item in data:
                cache_key_id = f"{cache_key}:{item[id_name]}"
                if not await cache.ahas_key(cache_key_id):
                    cached_data[cache_key_id] = item
                data_ids.append(item[id_name])
            cached_data[cache_key_page] = data_ids
            await cache.aset_many(cached_data, 100, None)
            return await self.get_apaginated_response(data) if page is not None else Response(
                data, status=status.HTTP_200_OK
            )
        cached_ids = await cache.aget(cache_key_page)
        data = await cache.aget_many((f"{cache_key}:{id}" for id in cached_ids))
        data = tuple(data.values())
        if hasattr(self, "pagination_class"):
            return await self.get_apaginated_response(
                await self.apaginate_queryset(data)
            )
        return Response(data, status=status.HTTP_200_OK)


class RetrieveModelMixin(mixins.RetrieveModelMixin):
    async def aretrieve(self, request, *args, **kwargs):
        cache_key = f"{await generate_cache_key(self)}:{self.kwargs['pk']}"
        if await cache.ahas_key(cache_key):
            return Response(await cache.aget(cache_key), status=status.HTTP_200_OK)
        instance = await self.aget_object()
        data = await get_data(self.get_serializer(instance, many=False))
        await cache.aset(cache_key, data)
        return Response(data, status=status.HTTP_200_OK)


class CreateModelMixin(mixins.CreateModelMixin):
    async def acreate(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        await sync_to_async(serializer.is_valid)(raise_exception=True)
        await self.perform_acreate(serializer)
        data = await get_data(serializer)
        headers = self.get_success_headers(data)
        id_name = getattr(self.serializer_class, "custom_id", "id")
        cache_key = f"{await generate_cache_key(self)}:{data[id_name]}"
        await cache.aset(cache_key, data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)


class UpdateModelMixin(mixins.UpdateModelMixin):
    async def aupdate(self, request, *args, **kwargs):
        response = await mixins.UpdateModelMixin.aupdate(self, request, *args, **kwargs)
        await cache.aset(
            f"{await generate_cache_key(self)}:{self.kwargs['pk']}",
            response.data
        )
        return response


class DestroyModelMixin(mixins.DestroyModelMixin):
    async def adestroy(self, request, *args, **kwargs):
        response = await mixins.DestroyModelMixin.adestroy(self, request, *args, **kwargs)
        cache_key = f"{await generate_cache_key(self)}:{self.kwargs['pk']}"
        if await cache.ahas_key(cache_key):
            await cache.adelete(cache_key)
        return response


class ReadOnlyModelViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    """
    A viewset that provides default asynchronous `list()` and `retrieve()` actions.
    """
    pass


class CachedModelViewSet(
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    GenericViewSet,
):
    """
    A viewset that provides default asynchronous `create()`, `retrieve()`, `update()`,
    `partial_update()`, `destroy()` and `list()` actions.
    """
    pass


class CacheMixinBase:
    async def _generate_cache_key(self):
        return md5(self.__class__.__name__.lower().encode()).hexdigest()

    async def _generate_request_cache_key(self, request):
        cache_key = md5(request.get_full_path().encode()).hexdigest()
        if isinstance(self, Owned):
            cache_key = f'{cache_key}:{md5(str(request.user.id).encode()).hexdigest()}'
        return cache_key


class ListMixin(CacheMixinBase):
    async def get(self, request, *args, **kwargs):
        cache_key_page = await self._generate_request_cache_key(request)
        cache_key = await self._generate_cache_key()
        paginator_cls = getattr(self, "pagination_class", None)
        if paginator_cls:
            paginator = paginator_cls()
            paginator.request = request
            if "LimitOffset" in paginator_cls.__name__:
                paginator.offset = paginator.get_offset(request)
                paginator.limit = paginator.get_limit(request)

        if not await cache.ahas_key(cache_key_page):
            queryset = self.filter_queryset(self.get_queryset())
            data = await sync_to_async(getattr)(self.get_serializer(
                queryset if not paginator else await paginator.paginate_queryset(
                    queryset, request, view=self
                ), many=True
            ), 'data')
            id_name = getattr(self.serializer_class, "custom_id", "id")
            items = data.get("results", data) if isinstance(data, dict) else data
            data_ids, cached_data = [], {}
            for item in items:
                cache_key_id = f"{cache_key}:{item[id_name]}"
                if not await cache.ahas_key(cache_key_id):
                    cached_data[cache_key_id] = item
                data_ids.append(item[id_name])
            cached_data[cache_key_page] = data_ids
            await cache.aset_many(cached_data, 100, None)
            return await sync_to_async(paginator.get_paginated_response)(data)

        cached_ids = await cache.aget(cache_key_page)
        data = await cache.aget_many((f"{cache_key}:{id}" for id in cached_ids))
        data = tuple(data.values())
        if paginator_cls:
            if "LimitOffset" in paginator_cls.__name__:
                paginator.count = await self.get_queryset().acount()
            else:
                paginator.page = data
            return await sync_to_async(paginator.get_paginated_response)(data)
        return Response(data)


class CreateMixin(CacheMixinBase):
    async def post(self, request, *args, **kwargs):
        resp = await self.acreate(request, *args, **kwargs)
        id_name = getattr(self.serializer_class, "custom_id", "id")
        cache_key = f"{await self._generate_cache_key()}:{resp.data[id_name]}"
        await cache.aset(cache_key, resp.data)
        return resp


class RetrieveMixin(CacheMixinBase):
    async def retrieve(self, request, *args, **kwargs):
        cache_key = f"{await self._generate_cache_key()}:{self.kwargs['pk']}"
        if await cache.ahas_key(cache_key):
            return Response(await cache.aget(cache_key))
        else:
            serializer = self.get_serializer()
            response = Response(await sync_to_async(
                serializer.to_representation
            )(await self.aget_object()))
            await cache.aset(cache_key, response.data)
            return response


class UpdateMixin(CacheMixinBase):
    async def aupdate(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = await self.aget_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        await sync_to_async(serializer.is_valid)(raise_exception=True)
        await serializer.asave()
        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}
        return Response(
            await sync_to_async(getattr)(serializer, 'data'),
            status=status.HTTP_200_OK
        )

    async def patch(self, request, *args, **kwargs):
        cache_key = f"{await self._generate_cache_key()}:{self.kwargs['pk']}"
        kwargs["partial"] = True
        resp = await self.aupdate(request, *args, **kwargs)
        await cache.aset(cache_key, resp.data)
        return resp

    async def put(self, request, *args, **kwargs):
        cache_key = f"{await self._generate_cache_key()}:{self.kwargs['pk']}"
        resp = await self.aupdate(request, *args, **kwargs)
        await cache.aset(cache_key, resp.data)
        return resp


class DestroyMixin(CacheMixinBase):
    async def delete(self, request, *args, **kwargs):
        cache_key = f"{await self._generate_cache_key()}:{self.kwargs['pk']}"
        instance = await self.aget_object()
        await instance.adelete()
        resp = Response(status=status.HTTP_204_NO_CONTENT)
        if await cache.ahas_key(cache_key):
            await cache.adelete(cache_key)
        return resp


class ListCreateMixin(ListModelMixin, CreateMixin):
    pass


class ReadUpdateMixin(RetrieveMixin, UpdateMixin):
    pass


class RetrieveDestroyMixin(RetrieveMixin, DestroyMixin):
    pass


class RetrieveUpdateDestroyMixin(RetrieveMixin, UpdateMixin, DestroyMixin):
    pass


class CacheMixin(
    ListMixin, CreateMixin, RetrieveMixin, UpdateMixin, DestroyMixin
):
    pass
