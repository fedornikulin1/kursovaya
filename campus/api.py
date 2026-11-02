"""REST adapters reuse the same reservation state machine as the website."""

from django.core.exceptions import ValidationError as ModelValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, permissions, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from drf_spectacular.utils import extend_schema

from ads.api.serializers import AdSerializer, ConversationSerializer
from ads.models import Ad
from ads.selectors import conversations
from .models import CampusPlace, Meeting, StudyRequest
from .selectors import ranked_matches
from .services import meeting_action, propose_meeting, respond_to_request


class OfferRequestSerializer(serializers.Serializer):
    ad = serializers.IntegerField(min_value=1)


class PlaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampusPlace
        fields = ["id", "name", "meeting_hint"]


class RequestSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.first_name", read_only=True)

    class Meta:
        model = StudyRequest
        fields = [
            "id",
            "author",
            "author_name",
            "title",
            "subject",
            "course",
            "semester",
            "mode",
            "description",
            "place",
            "available_from",
            "available_until",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "author", "created_at"]

    def validate(self, attrs):
        candidate = StudyRequest(author=self.context["request"].user)
        if self.instance:
            for field in self.Meta.fields:
                if hasattr(candidate, field) and field not in self.Meta.read_only_fields:
                    setattr(candidate, field, getattr(self.instance, field))
        for field, value in attrs.items():
            setattr(candidate, field, value)
        if candidate.place_id and not candidate.place.is_active:
            raise serializers.ValidationError({"place": "Это место недоступно."})
        try:
            candidate.full_clean()
        except ModelValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", exc.messages)) from exc
        return attrs


class RequestOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or obj.author_id == request.user.pk


class MatchSerializer(serializers.Serializer):
    ad = AdSerializer(read_only=True)
    score = serializers.IntegerField(read_only=True)
    reasons = serializers.ListField(child=serializers.CharField(), read_only=True)


class RequestViewSet(viewsets.ModelViewSet):
    serializer_class = RequestSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, RequestOwner]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StudyRequest.objects.none()
        visible = Q(is_active=True)
        if self.request.user.is_authenticated:
            visible |= Q(author=self.request.user)
        return StudyRequest.objects.filter(visible).select_related("author", "place")

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @extend_schema(request=OfferRequestSerializer, responses=ConversationSerializer)
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def offer(self, request, pk=None):
        data = OfferRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        ad = get_object_or_404(Ad, pk=data.validated_data["ad"], author=request.user)
        try:
            thread = respond_to_request(study_request=self.get_object(), ad=ad, user=request.user)
        except ModelValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(ConversationSerializer(thread).data)

    @extend_schema(responses=MatchSerializer(many=True))
    @action(detail=True, permission_classes=[permissions.IsAuthenticated])
    def matches(self, request, pk=None):
        need = self.get_object()
        if need.author_id != request.user.pk:
            self.permission_denied(request)
        results = ranked_matches(need, request.user) if need.is_active else []
        return Response(
            MatchSerializer(results, many=True, context=self.get_serializer_context()).data
        )


class PlaceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CampusPlace.objects.filter(is_active=True)
    serializer_class = PlaceSerializer
    pagination_class = None


class MeetingSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(read_only=True)
    effective_status = serializers.CharField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    place_name = serializers.CharField(source="place.name", read_only=True)

    class Meta:
        model = Meeting
        fields = [
            "id",
            "conversation",
            "ad",
            "proposed_by",
            "place",
            "place_name",
            "starts_at",
            "ends_at",
            "return_on",
            "is_loan",
            "study_request",
            "status",
            "effective_status",
            "status_label",
            "is_overdue",
            "updated_at",
        ]
        read_only_fields = fields


class MeetingInputSerializer(serializers.Serializer):
    conversation = serializers.IntegerField(min_value=1)
    place = serializers.PrimaryKeyRelatedField(queryset=CampusPlace.objects.filter(is_active=True))
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    return_on = serializers.DateField(required=False, allow_null=True)
    study_request = serializers.PrimaryKeyRelatedField(
        queryset=StudyRequest.objects.filter(is_active=True), required=False, allow_null=True
    )


class MeetingActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["confirm", "cancel", "handover", "receive", "return", "finish_return"]
    )


class MeetingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = MeetingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Meeting.objects.none()
        return Meeting.objects.filter(
            Q(conversation__user=self.request.user) | Q(ad__author=self.request.user)
        ).select_related("place")

    @extend_schema(request=MeetingInputSerializer, responses={201: MeetingSerializer})
    def create(self, request, *args, **kwargs):
        data = MeetingInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        thread = get_object_or_404(conversations(request.user), pk=values.pop("conversation"))
        try:
            meeting = propose_meeting(conversation=thread, user=request.user, **values)
        except ModelValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(MeetingSerializer(meeting).data, status=201)

    @extend_schema(request=MeetingActionSerializer, responses=MeetingSerializer)
    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        data = MeetingActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            meeting = meeting_action(
                meeting=self.get_object(), user=request.user, **data.validated_data
            )
        except ModelValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(MeetingSerializer(meeting).data)


router = DefaultRouter()
router.register("places", PlaceViewSet, basename="campus-place")
router.register("requests", RequestViewSet, basename="campus-request")
router.register("meetings", MeetingViewSet, basename="campus-meeting")
urlpatterns = router.urls
