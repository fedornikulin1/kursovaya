from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Avg, Count
from rest_framework import serializers

from ads.forms import RegisterForm
from ads.models import Ad, AdImage, Category, Message, Response, Review, UserProfile
from ads.services import create_review, profile_for, save_ad, start_conversation

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    first_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password1 = serializers.CharField(write_only=True, trim_whitespace=False)
    password2 = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        self.form = RegisterForm(attrs)
        if not self.form.is_valid():
            raise serializers.ValidationError(self.form.errors)
        return attrs

    def create(self, validated_data):
        return self.form.save()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "date_joined"]
        read_only_fields = fields


class PublicProfileSerializer(UserSerializer):
    faculty = serializers.CharField(source="profile.faculty", read_only=True, default="")
    bio = serializers.CharField(source="profile.bio", read_only=True, default="")
    rating = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["faculty", "bio", "rating"]

    def get_rating(self, obj) -> dict:
        return obj.reviews_received.aggregate(average=Avg("rating"), count=Count("id"))


class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    first_name = serializers.CharField(
        max_length=150, required=False, write_only=True, allow_blank=True
    )
    last_name = serializers.CharField(
        max_length=150, required=False, write_only=True, allow_blank=True
    )

    class Meta:
        model = UserProfile
        fields = [
            "user",
            "first_name",
            "last_name",
            "bio",
            "faculty",
            "group",
            "role",
            "phone",
            "show_phone",
            "reduce_motion",
            "telegram",
        ]

    def update(self, instance, validated_data):
        from django.db import transaction

        with transaction.atomic():
            for field in ("first_name", "last_name"):
                if field in validated_data:
                    setattr(instance.user, field, validated_data.pop(field))
            instance.user.save(update_fields=["first_name", "last_name"])
            return super().update(instance, validated_data)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "icon"]


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdImage
        fields = ["id", "image", "position"]
        read_only_fields = fields


class AdSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    images = ImageSerializer(many=True, read_only=True)
    is_favorite = serializers.BooleanField(read_only=True, default=False)
    price_label = serializers.CharField(read_only=True)

    class Meta:
        model = Ad
        fields = [
            "id",
            "title",
            "description",
            "price",
            "price_type",
            "price_label",
            "kind",
            "status",
            "image",
            "images",
            "category",
            "category_name",
            "author",
            "location",
            "is_study",
            "subject",
            "course",
            "semester",
            "campus_place",
            "available_from",
            "available_until",
            "exchange_for",
            "condition",
            "created_at",
            "updated_at",
            "is_favorite",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"image": {"allow_null": True, "required": False}}
        # Model.clean normalizes price first; constraints are checked in save_ad.
        validators = []

    def validate_category(self, category):
        if not category.is_active and (
            not self.instance or self.instance.category_id != category.pk
        ):
            raise serializers.ValidationError("Категория недоступна.")
        return category

    def _save(self, instance, data):
        for key, value in data.items():
            setattr(instance, key, value)
        try:
            return save_ad(ad=instance, author=self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", exc.messages)) from exc

    def create(self, validated_data):
        return self._save(Ad(author=self.context["request"].user), validated_data)

    def update(self, instance, validated_data):
        return self._save(instance, validated_data)


class PhotoUploadSerializer(serializers.Serializer):
    images = serializers.ListField(child=serializers.ImageField(), min_length=1, max_length=8)


class ContactsSerializer(serializers.Serializer):
    phone = serializers.CharField(allow_null=True)
    telegram = serializers.CharField(allow_null=True)
    contact_info = serializers.CharField()


class FavoriteStateSerializer(serializers.Serializer):
    is_favorite = serializers.BooleanField()


class MessageInputSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000)


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ["id", "sender", "text", "created_at", "read_at"]
        read_only_fields = fields


class ConversationCreateSerializer(MessageInputSerializer):
    ad = serializers.PrimaryKeyRelatedField(queryset=Ad.objects.filter(status="active"))

    def create(self, validated_data):
        try:
            return start_conversation(user=self.context["request"].user, **validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class ConversationSerializer(serializers.ModelSerializer):
    ad_title = serializers.CharField(source="ad.title", read_only=True)
    seller = UserSerializer(source="ad.author", read_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = Response
        fields = [
            "id",
            "ad",
            "ad_title",
            "seller",
            "user",
            "is_accepted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ReviewSerializer(serializers.ModelSerializer):
    from_user = UserSerializer(read_only=True)

    class Meta:
        model = Review
        fields = ["id", "from_user", "to_user", "response", "rating", "text", "created_at"]
        read_only_fields = ["id", "from_user", "response", "created_at"]
        validators = []

    def create(self, validated_data):
        try:
            return create_review(
                author=self.context["request"].user,
                recipient=validated_data.pop("to_user"),
                **validated_data,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
