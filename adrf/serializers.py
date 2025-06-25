import asyncio
from asgiref.sync import sync_to_async
from collections import OrderedDict
from asgiref.sync import sync_to_async
from django.db.models import Model
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.fields import SkipField
from rest_framework.fields import empty
from rest_framework import serializers as drf_serializers


class AsyncSerializerMixin:
    async def ais_valid(self, *, raise_exception=False):
        assert hasattr(self, "initial_data"), (
            "Cannot call `.is_valid()` as no `data=` keyword argument was "
            "passed when instantiating the serializer instance."
        )
        if not hasattr(self, "_validated_data"):
            try:
                self._validated_data = await self.arun_validation(self.initial_data)
            except ValidationError as exc:
                self._validated_data = {}
                self._errors = exc.detail
            else:
                self._errors = {}
        if self._errors and raise_exception:
            raise ValidationError(self.errors)
        return not bool(self._errors)

    async def arun_validation(self, data=empty):
        (is_empty_value, data) = self.validate_empty_values(data)
        if is_empty_value:
            return data
        value = self.to_internal_value(data)
        try:
            self.run_validators(value)
            value = await self.avalidate(value)
            assert value is not None, ".validate() should return the validated data"
        except (ValidationError, DjangoValidationError) as exc:
            raise ValidationError(detail=drf_serializers.as_serializer_error(exc))
        return value

    async def ato_representation(self, instance):
        ret = OrderedDict()
        fields = self._readable_fields

        for field in fields:
            try:
                attribute = await sync_to_async(field.get_attribute)(instance)
            except SkipField:
                continue

            check_for_none = (
                attribute.pk if isinstance(attribute, Model) else attribute
            )
            if check_for_none is None:
                ret[field.field_name] = None
            else:
                if asyncio.iscoroutinefunction(
                    getattr(field, "ato_representation", None)
                ):
                    repr = await field.ato_representation(attribute)
                else:
                    # Use sync_to_async to make synchronous operations async-safe
                    repr = await sync_to_async(field.to_representation)(attribute)

                ret[field.field_name] = repr

        return ret
