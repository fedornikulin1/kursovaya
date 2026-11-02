"""Validated forms used by the server-rendered website."""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.db import transaction

from .models import Ad, AdImage, Category, Review, UserProfile
from .validators import MAX_IMAGES, validate_image

User = get_user_model()


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        values = data if isinstance(data, (list, tuple)) else [data]
        result = []
        for value in values:
            try:
                cleaned = super().clean(value, initial)
                validate_image(cleaned)
            except forms.ValidationError as exc:
                raise forms.ValidationError(
                    [f"{value.name}: {message}" for message in exc.messages]
                ) from exc
            result.append(cleaned)
        return result


class RegisterForm(UserCreationForm):
    email = forms.EmailField(label="Электронная почта")
    first_name = forms.CharField(label="Имя", max_length=150)

    class Meta(UserCreationForm.Meta):
        fields = ("username", "first_name", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Эта почта уже используется.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            UserProfile.objects.get_or_create(user=user)
        return user


class AdForm(forms.ModelForm):
    STUDY_FIELDS = ("subject", "course", "semester", "exchange_for")

    @property
    def main_fields(self):
        return [
            self[name]
            for name in self.fields
            if name not in (*self.STUDY_FIELDS, "is_study", "image", "photos", "delete_photos")
        ]

    @property
    def study_fields(self):
        return [self[name] for name in self.STUDY_FIELDS]

    delete_photos = forms.ModelMultipleChoiceField(queryset=AdImage.objects.none(), required=False)
    photos = MultipleImageField(
        label="Дополнительные фотографии",
        required=False,
        help_text="JPEG, PNG или WebP, до 5 МБ каждая. Всего до 8 фотографий.",
    )

    class Meta:
        model = Ad
        fields = [
            "title",
            "kind",
            "category",
            "description",
            "is_study",
            "subject",
            "course",
            "semester",
            "campus_place",
            "available_from",
            "available_until",
            "exchange_for",
            "price_type",
            "price",
            "condition",
            "location",
            "image",
            "contact_info",
            "status",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "available_from": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
            "available_until": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["delete_photos"].queryset = (
            self.instance.images.all() if self.instance.pk else AdImage.objects.none()
        )
        categories = Category.objects.filter(is_active=True)
        if self.instance.pk:
            from django.db.models import Q

            categories = Category.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.category_id)
            )
        self.fields["category"].queryset = categories
        for name in ("kind", "price_type"):
            self.fields[name].widget.attrs["data-jelly-select"] = ""
        self.fields["price"].widget.attrs.update({"min": 0, "step": "0.01"})
        self.fields["image"].widget.attrs["accept"] = "image/jpeg,image/png,image/webp"
        self.fields["photos"].widget.attrs["accept"] = "image/jpeg,image/png,image/webp"
        from campus.models import CampusPlace

        self.fields["campus_place"].queryset = CampusPlace.objects.filter(is_active=True)
        self.fields["is_study"].help_text = (
            "Добавит объявление в учебный обмен и подбор по предмету."
        )
        self.fields["available_until"].help_text = (
            "Необязательно. Укажите оба времени, если готовы встречаться в определённый интервал (время Якутска)."
        )

    def clean(self):
        data = super().clean()
        if data.get("kind") in (Ad.Kind.GIVE, Ad.Kind.EXCHANGE, Ad.Kind.LEND):
            data["price_type"] = Ad.PriceType.FREE
            data["price"] = 0
        photos = data.get("photos", [])
        existing = (self.instance.images.count() if self.instance.pk else 0) - len(
            data.get("delete_photos", [])
        )
        if existing + bool(data.get("image")) + len(photos) > MAX_IMAGES:
            raise forms.ValidationError(f"Можно загрузить не больше {MAX_IMAGES} фотографий.")
        return data


class SettingsForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["phone", "show_phone", "telegram", "reduce_motion"]

    def clean(self):
        data = super().clean()
        if data.get("show_phone") and not data.get("phone"):
            self.add_error("phone", "Укажите номер, чтобы разрешить звонки.")
        return data


class MessageForm(forms.Form):
    text = forms.CharField(
        label="Сообщение",
        max_length=4000,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Здравствуйте! Объявление ещё актуально?"}
        ),
    )


class ReviewForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rating"].choices = [(value, str(value)) for value in range(1, 6)]

    class Meta:
        model = Review
        fields = ["rating", "text"]
        widgets = {
            "rating": forms.RadioSelect(),
            "text": forms.Textarea(attrs={"rows": 4}),
        }


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)

    class Meta:
        model = UserProfile
        fields = [
            "first_name",
            "last_name",
            "faculty",
            "group",
            "role",
            "bio",
            "phone",
            "show_phone",
            "telegram",
        ]
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = self.instance.user.first_name
        self.fields["last_name"].initial = self.instance.user.last_name

    @transaction.atomic
    def save(self, commit=True):
        profile = super().save(commit=False)
        if commit:
            user = profile.user
            user.first_name = self.cleaned_data["first_name"]
            user.last_name = self.cleaned_data["last_name"]
            user.save(update_fields=["first_name", "last_name"])
            profile.save()
        return profile
