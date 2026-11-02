"""Versioned support endpoints reusable by a future mobile client."""

from django.core.exceptions import ValidationError as DomainValidationError
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from .models import SupportMessage, SupportTicket
from .selectors import tickets_for
from .services import create_ticket, mark_answers_read, reply_ticket, set_status


class TicketSerializer(serializers.ModelSerializer):
    unread_answers = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = SupportTicket
        fields = ["id", "subject", "topic", "status", "created_at", "updated_at", "unread_answers"]
        read_only_fields = fields


class CreateTicketSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=150)
    topic = serializers.ChoiceField(choices=SupportTicket.Topic.choices)
    text = serializers.CharField(max_length=4000)


class ReplySerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000)


class SupportMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportMessage
        fields = ["id", "text", "from_staff", "created_at", "read_at"]
        read_only_fields = fields


def domain_call(function, **kwargs):
    try:
        return function(**kwargs)
    except DomainValidationError as exc:
        raise serializers.ValidationError({"detail": exc.messages}) from exc


class TicketViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = TicketSerializer
    queryset = SupportTicket.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return tickets_for(self.request.user)

    @extend_schema(request=CreateTicketSerializer, responses={201: TicketSerializer})
    def create(self, request):
        data = CreateTicketSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        ticket = domain_call(create_ticket, user=request.user, **data.validated_data)
        return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)

    @extend_schema(methods=["GET"], responses=SupportMessageSerializer(many=True))
    @extend_schema(
        methods=["POST"], request=ReplySerializer, responses={201: SupportMessageSerializer}
    )
    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        ticket = self.get_object()
        if request.method == "POST":
            data = ReplySerializer(data=request.data)
            data.is_valid(raise_exception=True)
            message = domain_call(
                reply_ticket, ticket=ticket, actor=request.user, **data.validated_data
            )
            return Response(SupportMessageSerializer(message).data, status=status.HTTP_201_CREATED)
        page = self.paginate_queryset(ticket.messages.order_by("-pk"))
        return self.get_paginated_response(SupportMessageSerializer(page, many=True).data)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        mark_answers_read(self.get_object(), request.user)
        return Response(status=204)

    @extend_schema(request=None, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        ticket = set_status(ticket=self.get_object(), actor=request.user, closed=True)
        return Response(TicketSerializer(ticket).data)

    @extend_schema(request=None, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        ticket = set_status(ticket=self.get_object(), actor=request.user, closed=False)
        return Response(TicketSerializer(ticket).data)
