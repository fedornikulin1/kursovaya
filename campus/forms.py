from django import forms
from .models import CampusPlace, Meeting, StudyRequest


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
            "place_note",
            "available_from",
            "available_until",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "place_note": forms.TextInput(attrs={"placeholder": "Например, главный вход в ИМИ"}),
            "available_from": datetime_widget(),
            "available_until": datetime_widget(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["place"].queryset = CampusPlace.objects.filter(is_active=True)
        self.fields["place"].label = "Место из списка"
        self.fields["place"].empty_label = "Не выбрано"
        self.fields["place_note"].help_text = "Можно указать своё место без выбора из списка."
        self.fields["mode"].widget.attrs["data-jelly-select"] = ""


class MeetingForm(forms.Form):
    place_note = forms.CharField(
        label="Место встречи",
        max_length=Meeting._meta.get_field("place_note").max_length,
        widget=forms.TextInput(attrs={"placeholder": "Например, у входа в общежитие № 8/1"}),
    )
    starts_at = forms.DateTimeField(label="Начало встречи", widget=datetime_widget())
    return_on = forms.DateField(
        label="Вернуть до", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    def __init__(self, *args, conversation, **kwargs):
        super().__init__(*args, **kwargs)
        if conversation.ad.kind != "lend":
            self.fields.pop("return_on")
        else:
            self.fields["return_on"].required = True
