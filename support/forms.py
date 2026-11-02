from django import forms

from .models import SupportTicket


class TicketForm(forms.ModelForm):
    text = forms.CharField(
        label="Что случилось?",
        max_length=4000,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "Опишите ситуацию. Если вопрос об объявлении, добавьте ссылку на него.",
            }
        ),
    )

    class Meta:
        model = SupportTicket
        fields = ["topic", "subject"]
        widgets = {
            "subject": forms.TextInput(
                attrs={"placeholder": "Например: не получается загрузить фотографию"}
            )
        }


class ReplyForm(forms.Form):
    text = forms.CharField(
        label="Ваше сообщение",
        max_length=4000,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Дополните вопрос или ответьте поддержке…"}
        ),
    )
