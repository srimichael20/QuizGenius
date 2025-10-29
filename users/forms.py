from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Profile, QuizCategory, QuizSubcategory


class UserRegisterForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
            'password1': forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Pa'}),
            'password2': forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}),
        }

class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg bg-light bg-opacity-25 text-white border-0',
            'placeholder': 'Username or Email'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg bg-light bg-opacity-25 text-white border-0',
            'placeholder': 'Password'
        })
    )



class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
        }

class ProfileUpdateForm(forms.ModelForm):
    preferences = forms.CharField(widget=forms.HiddenInput(), required=False)
    class Meta:
        model = Profile
        fields = ['avatar', 'bio', 'gender', 'dob', 'location', 'preferences', 'theme']
        widgets = {
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Write something about yourself...'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'dob': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your city/country'}),
            'preferences': forms.HiddenInput(),  # handled by JS
            'theme': forms.Select(attrs={'class': 'form-select'}),
        }


class QuizStartForm(forms.Form):
    """
    Quiz Start Form with dynamic choices and Mixed/Single Quiz support
    """

    # ------------------ Fields ------------------
    category_choices_multi = forms.MultipleChoiceField(
        choices=[],
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '6'}),
        label="Select Multiple Categories (for Mixed Quiz)"
    )

    category_choice = forms.ChoiceField(
        choices=[],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Select Category"
    )
    category_new = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Or type new category'}),
        label="Or Enter New Category"
    )

    subcategory_choice = forms.ChoiceField(
        choices=[],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Select Subcategory"
    )
    subcategory_new = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Or type new subcategory'}),
        label="Or Enter New Subcategory"
    )

    difficulty = forms.ChoiceField(
        choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Difficulty"
    )

    question_count = forms.ChoiceField(
        choices=[(5, '5 Questions'), (10, '10 Questions'), (15, '15 Questions'), (20, '20 Questions')],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Number of Questions"
    )

    # ------------------ Init for dynamic choices ------------------
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        categories = list(QuizCategory.objects.all())
        subcategories = list(QuizSubcategory.objects.all())

        category_choices = [(c.id, c.name) for c in categories]
        category_choices.insert(0, ("", "Select existing category"))

        subcategory_choices = [(s.id, s.name) for s in subcategories]
        subcategory_choices.insert(0, ("", "Select existing subcategory"))

        self.fields['category_choices_multi'].choices = category_choices
        self.fields['category_choice'].choices = category_choices
        self.fields['subcategory_choice'].choices = subcategory_choices

    # ------------------ Clean ------------------
    def clean(self):
        cleaned_data = super().clean()
        multi_cats = cleaned_data.get("category_choices_multi")

        if multi_cats:
            cleaned_data["category"] = None
            cleaned_data["subcategory"] = None
            cleaned_data["is_mixed_quiz"] = True
            return cleaned_data

        # Single Category
        category_id = cleaned_data.get("category_choice")
        category_name = cleaned_data.get("category_new", "").strip()

        if category_name:
            category, _ = QuizCategory.objects.get_or_create(
                name=category_name,
                defaults={"description": "", "created_by_ai": False}
            )
        elif category_id:
            category = QuizCategory.objects.get(id=category_id)
        else:
            raise forms.ValidationError("Please select or enter a category.")

        cleaned_data["category"] = category

        # Subcategory
        subcategory_id = cleaned_data.get("subcategory_choice")
        subcategory_name = cleaned_data.get("subcategory_new", "").strip()

        if subcategory_name:
            subcategory, _ = QuizSubcategory.objects.get_or_create(
                category=category,
                name=subcategory_name,
                defaults={"description": "", "created_by_ai": False}
            )
        elif subcategory_id:
            subcategory = QuizSubcategory.objects.get(id=subcategory_id)
        else:
            raise forms.ValidationError("Please select or enter a subcategory.")

        cleaned_data["subcategory"] = subcategory
        cleaned_data["is_mixed_quiz"] = False
        return cleaned_data



