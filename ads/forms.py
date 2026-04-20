from django import forms
from .models import Ad, Response

class AdForm(forms.ModelForm):
    class Meta:
        model = Ad
        fields = ['title', 'description', 'price', 'image', 'category', 'contact_info']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'contact_info': forms.TextInput(attrs={'placeholder': 'Telegram: @username или +7...'}),
        }

class ResponseForm(forms.ModelForm):
    class Meta:
        model = Response
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Напишите ваш вопрос...'}),
        }

class ReplyForm(forms.ModelForm):
    class Meta:
        model = Response
        fields = ['reply']
        widgets = {
            'reply': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Ваш ответ...'}),
        }