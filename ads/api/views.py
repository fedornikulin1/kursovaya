from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response as APIResponse
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenBlacklistView

from ads.filters import AdFilter
from ads.models import Ad, AdImage, Category, Favorite, Review
from ads.selectors import catalogue, conversations, visible_ads
from ads.services import mark_read, profile_for, save_ad, send_message
from .serializers import (
    AdSerializer,
    CategorySerializer,
    ContactsSerializer,
    ConversationCreateSerializer,
    ConversationSerializer,
    FavoriteStateSerializer,
    ImageSerializer,
    MessageInputSerializer,
    MessageSerializer,
    PhotoUploadSerializer,
    ProfileSerializer,
    PublicProfileSerializer,
    RegisterSerializer,
    ReviewSerializer,
    UserSerializer,
)


class OwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or obj.author_id == request.user.pk


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(responses={201: UserSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return APIResponse(UserSerializer(user).data, status=201)


class LoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class LogoutView(TokenBlacklistView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProfileSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return profile_for(self.request.user)


class PublicProfileView(generics.RetrieveAPIView):
    serializer_class = PublicProfileSerializer
    queryset = get_user_model().objects.filter(is_active=True).select_related("profile")
    lookup_field = "username"


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(is_active=True)
    pagination_class = None


class AdViewSet(viewsets.ModelViewSet):
    serializer_class = AdSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, OwnerOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AdFilter

    def perform_destroy(self, instance):
        from ads.services import delete_ad

        try:
            delete_ad(ad=instance, user=self.request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Ad.objects.none()
        if self.action in ("list", "favorites"):
            return catalogue(self.request.user).filter(status="active")
        return visible_ads(self.request.user)

    @extend_schema(responses=AdSerializer(many=True))
    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def mine(self, request):
        queryset = catalogue(request.user).filter(author=request.user)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(responses=AdSerializer(many=True))
    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def favorites(self, request):
        queryset = self.get_queryset().filter(favorited_by__user=request.user)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(request=None, responses=FavoriteStateSerializer)
    @action(
        detail=True, methods=["post", "delete"], permission_classes=[permissions.IsAuthenticated]
    )
    def favorite(self, request, pk=None):
        ad = self.get_object()
        if request.method == "POST":
            Favorite.objects.get_or_create(user=request.user, ad=ad)
        else:
            Favorite.objects.filter(user=request.user, ad=ad).delete()
        return APIResponse({"is_favorite": request.method == "POST"})

    @extend_schema(responses=ContactsSerializer)
    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def contacts(self, request, pk=None):
        ad = self.get_object()
        profile = profile_for(ad.author)
        return APIResponse(
            {
                "phone": profile.phone if profile.show_phone and profile.phone else None,
                "telegram": profile.telegram or None,
                "contact_info": ad.contact_info,
            }
        )

    @extend_schema(request=PhotoUploadSerializer, responses={201: ImageSerializer(many=True)})
    @action(
        detail=True,
        methods=["post"],
        permission_classes=[permissions.IsAuthenticated, OwnerOrReadOnly],
    )
    def photos(self, request, pk=None):
        ad = self.get_object()
        serializer = PhotoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            save_ad(ad=ad, author=request.user, photos=serializer.validated_data["images"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return APIResponse(
            ImageSerializer(ad.images.all(), many=True, context=self.get_serializer_context()).data,
            status=201,
        )


class PhotoDeleteView(generics.DestroyAPIView):
    serializer_class = ImageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AdImage.objects.none()
        return AdImage.objects.filter(ad__author=self.request.user)


class ConversationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ConversationSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            from ads.models import Response

            return Response.objects.none()
        return conversations(self.request.user)

    def get_serializer_class(self):
        return ConversationCreateSerializer if self.action == "create" else ConversationSerializer

    @extend_schema(request=ConversationCreateSerializer, responses={201: ConversationSerializer})
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = serializer.save()
        return APIResponse(ConversationSerializer(conversation).data, status=201)

    @extend_schema(
        methods=["GET"],
        parameters=[
            OpenApiParameter(
                "after",
                int,
                description="Вернуть сообщения с id больше указанного, по возрастанию id.",
            )
        ],
        responses=MessageSerializer(many=True),
    )
    @extend_schema(
        methods=["POST"], request=MessageInputSerializer, responses={201: MessageSerializer}
    )
    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        conversation = self.get_object()
        if request.method == "POST":
            serializer = MessageInputSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            message = send_message(
                conversation=conversation, sender=request.user, **serializer.validated_data
            )
            return APIResponse(MessageSerializer(message).data, status=201)
        queryset = conversation.messages.select_related("sender").order_by("-created_at", "-pk")
        if "after" in request.query_params:
            try:
                after = int(request.query_params["after"])
                if after < 0:
                    raise ValueError
            except ValueError as exc:
                raise serializers.ValidationError(
                    {"after": "Укажите неотрицательное целое число."}
                ) from exc
            queryset = queryset.filter(pk__gt=after).order_by("pk")
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(MessageSerializer(page, many=True).data)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        mark_read(self.get_object(), request.user)
        return APIResponse(status=204)

    @extend_schema(request=None, responses=ConversationSerializer)
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        conversation = self.get_object()
        if conversation.ad.author_id != request.user.pk:
            self.permission_denied(request, message="Принять отклик может только автор объявления.")
        conversation.is_accepted = True
        conversation.save(update_fields=["is_accepted", "updated_at"])
        return APIResponse(ConversationSerializer(conversation).data)


class ReviewViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ReviewSerializer
    queryset = Review.objects.select_related("from_user", "to_user")
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["to_user"]
