from pathlib import Path

from django import forms
from django.conf import settings

from core.models import Chat, Job, Trigger


def _get_script_choices():
    scripts_dir = Path(settings.SCRIPTS_DIR)
    if not scripts_dir.exists():
        return []
    choices = [("", "-- Select script --")]
    for f in sorted(scripts_dir.glob("*.py")):
        choices.append((f.name, f.name))
    return choices


class JobForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = ["name", "description", "job_type", "script_path", "message_template", "target_chats", "reply_to_trigger_chat", "config_json"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "message_template": forms.Textarea(attrs={"rows": 3}),
            "target_chats": forms.CheckboxSelectMultiple,
            "config_json": forms.Textarea(attrs={"rows": 3, "placeholder": '{"key": "value"}'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["script_path"].widget = forms.Select(choices=_get_script_choices())
        self.fields["target_chats"].queryset = Chat.objects.all()
        self.fields["description"].required = False
        self.fields["script_path"].required = False
        self.fields["message_template"].required = False
        self.fields["config_json"].required = False


class TriggerForm(forms.ModelForm):
    class Meta:
        model = Trigger
        fields = ["trigger_type", "cron_expression", "pattern", "listen_chats"]
        widgets = {
            "listen_chats": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cron_expression"].required = False
        self.fields["pattern"].required = False
        self.fields["listen_chats"].required = False
        self.fields["listen_chats"].queryset = Chat.objects.all()


TriggerFormSet = forms.inlineformset_factory(
    Job,
    Trigger,
    form=TriggerForm,
    extra=1,
    can_delete=True,
)
