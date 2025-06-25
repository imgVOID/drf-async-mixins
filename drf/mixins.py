from hashlib import md5
from asgiref.sync import sync_to_async
from django.core.cache import cache
from rest_framework import mixins, status
from rest_framework.response import Response


async def generate_cache_key(view):
    model_name = view.get_serializer_class()
    return md5(model_name.Meta.model.__name__.lower().encode()).hexdigest()


async def generate_request_cache_key(request):
    cache_key = md5(request.get_full_path().encode()).hexdigest()
    return cache_key


class CreateModelMixin(mixins.CreateModelMixin):
    """
    Create a model instance.
    """

    async def acreate(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        await sync_to_async(serializer.is_valid)(raise_exception=True)
        await self.perform_acreate(serializer)
        data = await sync_to_async(getattr)(serializer, 'data')
        headers = self.get_success_headers(data)
        cache_key = f"{await generate_cache_key(self)}:{data[self.serializer_class.id]}"
        await cache.aset(cache_key, data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    async def perform_acreate(self, serializer):
        await sync_to_async(serializer.save)()


class ListModelMixin(mixins.ListModelMixin):
    """
    List a queryset.
    """

    async def alist(self, request, *args, **kwargs):
        cache_key_page = await generate_request_cache_key(request)
        cache_key = await generate_cache_key(self)
        if not await cache.ahas_key(cache_key_page):
            queryset = self.filter_queryset(self.get_queryset())
            page = await sync_to_async(self.paginate_queryset)(queryset)
            serializer = sync_to_async(self.get_serializer)(page or queryset, many=True)
            id_name = serializer.__class__.id
            data = await sync_to_async(getattr)(serializer, 'data')
            data_ids, cached_data = [], {}
            for item in data:
                cache_key_id = f"{cache_key}:{item[id_name]}"
                if not await cache.ahas_key(cache_key_id):
                    cached_data[cache_key_id] = item
                data_ids.append(item[id_name])
            cached_data[cache_key_page] = data_ids
            await cache.aset_many(cached_data, 100, None)
            if page:
                return await sync_to_async(self.get_paginated_response)(data)
            else:
                return Response(data, status=status.HTTP_200_OK)
        cached_ids = await cache.aget(cache_key_page)
        data = await cache.aget_many((f"{cache_key}:{id}" for id in cached_ids))
        data = tuple(data.values())
        if hasattr(self, "pagination_class"):
            return await sync_to_async(self.get_paginated_response)(
                await self.apaginate_queryset(data)
            )
        return Response(data, status=status.HTTP_200_OK)


class RetrieveModelMixin(mixins.RetrieveModelMixin):
    """
    Retrieve a model instance.
    """

    async def aretrieve(self, request, *args, **kwargs):
        cache_key = f"{await generate_cache_key(self)}:{self.kwargs['pk']}"
        if await cache.ahas_key(cache_key):
            return Response(await cache.aget(cache_key), status=status.HTTP_200_OK)
        instance = await sync_to_async(self.get_object)()
        serializer = self.get_serializer(instance, many=False)
        data = await sync_to_async(getattr)(serializer, data)
        await cache.aset(cache_key, data)
        return Response(data, status=status.HTTP_200_OK)


class UpdateModelMixin(mixins.UpdateModelMixin):
    """
    Update a model instance.
    """

    async def aupdate(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = await sync_to_async(self.get_object)()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        await sync_to_async(serializer.is_valid)(raise_exception=True)
        await self.perform_aupdate(serializer)
        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}
        data = await sync_to_async(getattr)(serializer, 'data')
        await cache.aset(f"{await generate_cache_key(self)}:{self.kwargs['pk']}", data)
        return Response(data, status=status.HTTP_200_OK)

    async def perform_aupdate(self, serializer):
        await sync_to_async(serializer.save)()

    async def partial_aupdate(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return await self.aupdate(request, *args, **kwargs)


class DestroyModelMixin(mixins.DestroyModelMixin):
    """
    Destroy a model instance.
    """

    async def adestroy(self, request, *args, **kwargs):
        instance = await sync_to_async(self.get_object)()
        await self.perform_adestroy(instance)
        cache_key = f"{await generate_cache_key(self)}:{self.kwargs['pk']}"
        if await cache.ahas_key(cache_key):
            await cache.adelete(cache_key)
        return Response(status=status.HTTP_204_NO_CONTENT)

    async def perform_adestroy(self, instance):
        await instance.adelete()
