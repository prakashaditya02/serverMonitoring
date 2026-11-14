from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import Threshold


class ThresholdForm(forms.ModelForm):
    recipients = forms.CharField(
        required=False,
        label="Recipients",
        help_text=(
            "Comma-separated email addresses. Leave blank to use the global "
            "alert recipient."
        ),
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "alerts@example.com, ops@example.com",
            }
        ),
    )

    class Meta:
        model = Threshold
        fields = [
            "server_instance",
            "cpu_threshold",
            "memory_threshold",
            "disk_threshold",
        ]
        widgets = {
            "server_instance": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "list": "known-servers",
                    "autocomplete": "off",
                    "placeholder": "server-hostname",
                }
            ),
            "cpu_threshold": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100, "step": "0.1"}
            ),
            "memory_threshold": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100, "step": "0.1"}
            ),
            "disk_threshold": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100, "step": "0.1"}
            ),
        }
        labels = {
            "server_instance": "Server instance",
            "cpu_threshold": "CPU limit (%)",
            "memory_threshold": "Memory limit (%)",
            "disk_threshold": "Disk limit (%)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            recipients = self.instance.recipients or []
            if isinstance(recipients, str):
                recipients = [recipients]
            self.fields["recipients"].initial = ", ".join(recipients)

    def clean_recipients(self):
        raw_recipients = self.cleaned_data.get("recipients", "")
        recipients = []
        for address in raw_recipients.replace(";", ",").replace("\n", ",").split(","):
            address = address.strip()
            if not address:
                continue
            try:
                validate_email(address)
            except ValidationError:
                raise forms.ValidationError(f"Invalid email address: {address}")
            if address not in recipients:
                recipients.append(address)
        return recipients

    def _clean_percentage(self, field_name):
        value = self.cleaned_data.get(field_name)
        if value is not None and not 0 <= value <= 100:
            raise forms.ValidationError("Enter a value between 0 and 100.")
        return value

    def clean_cpu_threshold(self):
        return self._clean_percentage("cpu_threshold")

    def clean_memory_threshold(self):
        return self._clean_percentage("memory_threshold")

    def clean_disk_threshold(self):
        return self._clean_percentage("disk_threshold")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.recipients = self.cleaned_data.get("recipients", [])
        if commit:
            instance.save()
            self.save_m2m()
        return instance
