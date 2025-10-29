# create_profiles.py
import os
from django.core.files import File
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_Quiz.settings')
django.setup()

from django.contrib.auth.models import User
from users.models import Profile

default_avatar_path = os.path.join('media', 'avatars', 'default_avatar.png')

for user in User.objects.all():
    profile, created = Profile.objects.get_or_create(user=user)

    # Only set avatar if empty
    if not profile.avatar or profile.avatar.name == '':
        with open(default_avatar_path, 'rb') as f:
            profile.avatar.save('avatars/default_avatar.png', File(f), save=True)

print("All profiles updated successfully!")
        