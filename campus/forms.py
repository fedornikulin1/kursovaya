from django import forms
from .models import CampusPlace, StudyRequest


def datetime_widget():
    return forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"})


class StudyRequestForm(forms.ModelForm):
    class Meta:
        model = StudyRequest
        fields = [
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
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "available_from": datetime_widget(),
            "available_until": datetime_widget(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["place"].queryset = CampusPlace.objects.filter(is_active=True)
        self.fields["mode"].widget.attrs["data-jelly-select"] = ""


class MeetingForm(forms.Form):
    place = forms.ModelChoiceField(
        label="Место встречи", queryset=CampusPlace.objects.filter(is_active=True)
    )
    starts_at = forms.DateTimeField(label="Начало встречи", widget=datetime_widget())
    ends_at = forms.DateTimeField(
        label="Конец интервала",
        widget=datetime_widget(),
        help_text="Интервал до 4 часов. Бронь действует до его конца.",
    )
    return_on = forms.DateField(
        label="Вернуть до", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    study_request = forms.ModelChoiceField(
        label="Закрыть запрос после получения", queryset=StudyRequest.objects.none(), required=False
    )

    def __init__(self, *args, conversation, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["study_request"].queryset = StudyRequest.objects.filter(
            author_id=conversation.user_id, is_active=True
        )
        if conversation.ad.kind != "lend":
            self.fields.pop("return_on")
        else:
            self.fields["return_on"].required = True
        self.fields["place"].initial = conversation.ad.campus_place_id
