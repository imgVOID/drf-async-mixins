import copy
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.db import models
from django.test import TestCase

from rest_framework import status
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from rest_framework.serializers import ModelSerializer
from .drf.viewsets import ModelViewSet, ViewSet
from .drf import generics


JSON_ERROR = "JSON parse error - Expecting value:"


def sanitise_json_error(error_dict):
    """
    Exact contents of JSON error messages depend on the installed version
    of json.
    """
    ret = copy.copy(error_dict)
    chop = len(JSON_ERROR)
    ret["detail"] = ret["detail"][:chop]
    return ret

factory = APIRequestFactory()


class BasicViewSet(ViewSet):
    def list(self, request):
        return Response({"method": "GET"})

    def create(self, request, *args, **kwargs):
        return Response({"method": "POST", "data": request.data})


class AsyncViewSet(ViewSet):
    async def list(self, request):
        return Response({"method": "GET"})

    async def create(self, request, *args, **kwargs):
        return Response({"method": "POST", "data": request.data})


class ViewSetIntegrationTests(TestCase):
    def setUp(self):
        self.list = BasicViewSet.as_view({"get": "list"})
        self.create = BasicViewSet.as_view({"post": "create"})

    def test_get_succeeds(self):
        request = factory.get("/")
        response = self.list(request)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"method": "GET"}

    def test_logged_in_get_succeeds(self):
        user = User.objects.create_user("user", "user@example.com", "password")
        request = factory.get("/")
        # del is used to force the ORM to query the user object again
        del user.is_active
        request.user = user
        response = self.list(request)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"method": "GET"}

    def test_post_succeeds(self):
        request = factory.post("/", {"test": "foo"})
        response = self.create(request)
        assert response.status_code == status.HTTP_200_OK
        assert "'test': ['foo']" in str(response.data)

    def test_options_succeeds(self):
        request = factory.options("/")
        response = self.list(request)
        assert response.status_code == status.HTTP_200_OK


class AsyncViewSetIntegrationTests(TestCase):
    def setUp(self):
        self.list = AsyncViewSet.as_view({"get": "list"})
        self.create = AsyncViewSet.as_view({"post": "create"})

    def test_get_succeeds(self):
        request = factory.get("/")
        response = async_to_sync(self.list)(request)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"method": "GET"}

    def test_logged_in_get_succeeds(self):
        user = User.objects.create_user("user", "user@example.com", "password")
        request = factory.get("/")
        # del is used to force the ORM to query the user object again
        del user.is_active
        request.user = user
        response = async_to_sync(self.list)(request)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"method": "GET"}

    def test_post_succeeds(self):
        request = factory.post("/", {"test": "foo"})
        response = async_to_sync(self.create)(request)
        assert response.status_code == status.HTTP_200_OK
        assert "{'test': ['foo']}" in str(response.data)

    def test_options_succeeds(self):
        request = factory.options("/")
        response = async_to_sync(self.list)(request)
        assert response.status_code == status.HTTP_200_OK

    def test_400_parse_error(self):
        request = factory.post("/", "f00bar", content_type="application/json")
        response = async_to_sync(self.create)(request)
        expected = {"detail": JSON_ERROR}
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert sanitise_json_error(response.data) == expected


class UserSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username",)


class UserViewSet(ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class ModelViewSetIntegrationTests(TestCase):
    def setUp(self):
        self.list_create = UserViewSet.as_view({"get": "alist", "post": "acreate"})
        self.retrieve_update = UserViewSet.as_view(
            {"get": "aretrieve", "put": "aupdate"}
        )
        self.destroy = UserViewSet.as_view({"delete": "adestroy"})

    def test_list_succeeds(self):
        User.objects.create(username="test")
        request = factory.get("/")
        response = async_to_sync(self.list_create)(request)
        assert response.status_code == status.HTTP_200_OK
        assert "username" in response.data["results"][0].keys()
        assert "test" in response.data["results"][0].values()

    def test_create_succeeds(self):
        request = factory.post("/", data={"username": "test"})
        response = async_to_sync(self.list_create)(request)
        assert response.status_code == status.HTTP_201_CREATED
        assert "username" in response.data.keys()
        assert "test" in response.data.values()

    def test_retrieve_succeeds(self):
        user = User.objects.create(username="test")
        request = factory.get("/")
        response = async_to_sync(self.retrieve_update)(request, pk=user.id)
        assert response.status_code == status.HTTP_200_OK
        assert "username" in response.data.keys()
        assert "test" in response.data.values()

    def test_update_succeeds(self):
        user = User.objects.create(username="test")
        request = factory.put("/", data={"username": "not-test"})
        response = async_to_sync(self.retrieve_update)(request, pk=user.id)
        assert response.status_code == status.HTTP_200_OK
        assert "username" in response.data.keys()
        assert "not-test" in response.data.values()

    def test_destroy_succeeds(self):
        user = User.objects.create(username="test")
        request = factory.delete("/")
        response = async_to_sync(self.destroy)(request, pk=user.id)
        assert response.status_code == status.HTTP_204_NO_CONTENT


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username",)


class CreateUserView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class ListUserView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class RetrieveUserView(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class DestroyUserView(generics.DestroyAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class UpdateUserView(generics.UpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class TestCreateUserView(TestCase):
    def setUp(self):
        self.view = CreateUserView.as_view()

    def test_post_succeeds(self):
        request = factory.post("/", {"username": "test"})
        response = async_to_sync(self.view)(request)
        assert response.status_code == status.HTTP_201_CREATED
        assert "'username': 'test'" in str(response.data)


class TestRetrieveUserView(TestCase):
    def setUp(self):
        self.view = RetrieveUserView.as_view()

    def test_get_no_users(self):
        request = factory.get("/")
        response = async_to_sync(self.view)(request, pk=1)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_one_user(self):
        user = User.objects.create(username="test")
        request = factory.get("/")
        response = async_to_sync(self.view)(request, pk=user.id)
        assert response.status_code == status.HTTP_200_OK
        assert "username" in response.data.keys()
        assert "test" in response.data.values()


class TestDestroyUserView(TestCase):
    def setUp(self):
        self.view = DestroyUserView.as_view()

    def test_delete_no_users(self):
        request = factory.delete("/")
        response = async_to_sync(self.view)(request, pk=1)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_one_user(self):
        user = User.objects.create(username="test")
        request = factory.delete("/")
        response = async_to_sync(self.view)(request, pk=user.id)
        assert response.status_code == status.HTTP_204_NO_CONTENT


class TestUpdateUserView(TestCase):
    def setUp(self):
        self.view = UpdateUserView.as_view()

    def test_update_user(self):
        user = User.objects.create(username="test")
        request = factory.put("/", data={"username": "not-test"})
        response = async_to_sync(self.view)(request, pk=user.id)
        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.username == "not-test"
