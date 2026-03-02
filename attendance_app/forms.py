from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from .models import LocalMember, LocalAttendance, LocalMember
from datetime import date, timedelta


class LoginForm(AuthenticationForm):
    """Custom login form"""
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username',
            'autofocus': True
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )


class UserRegistrationForm(UserCreationForm):
    """User registration form"""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email'
        })
    )
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First Name'
        })
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last Name'
        })
    )
    
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Username'})
        self.fields['password1'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Password'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Confirm Password'})


class MemberSearchForm(forms.Form):
    """Search members form"""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name or email...',
            'autocomplete': 'off'
        })
    )
    
    filter_active = forms.ChoiceField(
        required=False,
        choices=[
            ('all', 'All Members'),
            ('active', 'Active Only'),
            ('inactive', 'Inactive Only'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    filter_face = forms.ChoiceField(
        required=False,
        choices=[
            ('all', 'All'),
            ('registered', 'Face Registered'),
            ('not_registered', 'Face Not Registered'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    belt_rank = forms.ChoiceField(
        required=False,
        choices=[('', 'All Belts')] + LocalMember.BELT_RANKS,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class ManualCheckinForm(forms.Form):
    """Manual check-in form"""
    member_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=True
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes...'
        })
    )


class DateRangeForm(forms.Form):
    """Date range selection for reports"""
    date_from = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        initial=date.today - timedelta(days=30)
    )
    
    date_to = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        initial=date.today
    )
    
    member_type = forms.ChoiceField(
        required=False,
        choices=[
            ('all', 'All Members'),
            ('adult', 'Adults Only'),
            ('child', 'Children Only'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial='all'
    )


class FaceRegistrationForm(forms.Form):
    """Face registration form"""
    member = forms.ModelChoiceField(
        queryset=LocalMember.objects.filter(is_active=True, face_registered=False),
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'member-select'
        }),
        empty_label="Select a member..."
    )
    
    num_photos = forms.IntegerField(
        required=False,
        min_value=3,
        max_value=10,
        initial=5,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 3,
            'max': 10
        })
    )


class BulkCheckinForm(forms.Form):
    """Bulk check-in form"""
    member_ids = forms.MultipleChoiceField(
        required=True,
        widget=forms.CheckboxSelectMultiple,
        choices=[]
    )
    
    check_in_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        initial=date.today
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes for all check-ins...'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        members = LocalMember.objects.filter(is_active=True).order_by('last_name', 'first_name')
        choices = [(m.id, f"{m.last_name}, {m.first_name}") for m in members]
        self.fields['member_ids'].choices = choices


class SettingsForm(forms.Form):
    """System settings form"""
    # Sync settings
    pythonanywhere_url = forms.URLField(
        required=True,
        widget=forms.URLInput(attrs={'class': 'form-control'}),
        label="PythonAnywhere URL"
    )
    
    pythonanywhere_api_key = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="API Key"
    )
    
    sync_interval = forms.IntegerField(
        required=True,
        min_value=60,
        max_value=3600,
        initial=300,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label="Sync Interval (seconds)"
    )
    
    # Face recognition settings
    face_threshold = forms.FloatField(
        required=True,
        min_value=0.3,
        max_value=0.9,
        initial=0.6,
        step=0.05,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 0.05}),
        label="Face Recognition Threshold"
    )
    
    min_face_photos = forms.IntegerField(
        required=True,
        min_value=2,
        max_value=10,
        initial=3,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label="Minimum Face Photos"
    )
    
    # Camera settings
    camera_index = forms.IntegerField(
        required=True,
        min_value=0,
        max_value=10,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label="Camera Index"
    )
    
    # Display settings
    items_per_page = forms.IntegerField(
        required=True,
        min_value=10,
        max_value=100,
        initial=25,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label="Items Per Page"
    )
    
    dark_mode = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Enable Dark Mode"
    )