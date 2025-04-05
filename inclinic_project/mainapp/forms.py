from django import forms
from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV3

class ExampleForm(forms.Form):
    name = forms.CharField(max_length=100)
    captcha = ReCaptchaField(widget=ReCaptchaV3, label='')

