# users/models.py
from django.db import models
from django.contrib.auth.models import User
from PIL import Image
import os

# Profile Model
class Profile(models.Model):
    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
        ("prefer_not_say", "Prefer not to say"),
    ]

    THEME_CHOICES = [
        ("default", "Default"),
        ('dark', 'Dark'),
        ('gradient', 'Gradient'),
        ('animated-stars', 'Animated Stars'),
        ("confetti", "🎉 Confetti"),       # New
        ("particles", "✨ Particles"),     # New
        ("galaxy", "Galaxy"),
        ("matrix", "Matrix"),
        ("aurora", "Aurora"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    avatar = models.ImageField(default='avatars/default_avatar.png', upload_to='avatars/')
    bio = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, null=True)
    preferences = models.TextField(blank=True, null=True)  # AI personalization data
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default="default")

    # ---- Add AI tip caching fields ----
    ai_tip_text = models.TextField(blank=True, null=True)
    ai_tip_date = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

    @property
    def avatar_url(self):
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        return '/media/avatars/default_avatar.png'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.avatar and os.path.exists(self.avatar.path):
            img = Image.open(self.avatar.path)
            if img.height > 300 or img.width > 300:
                output_size = (300, 300)
                img.thumbnail(output_size)
                img.save(self.avatar.path)

# ==============================
# QUIZ CATEGORY / SUBCATEGORY
# ==============================
class QuizCategory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="categories", null=True, blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_by_ai = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        unique_together = ('user', 'name')  # unique per user


class QuizSubcategory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subcategories", null=True, blank=True)
    category = models.ForeignKey(QuizCategory, on_delete=models.CASCADE, related_name="subcategories", null=True, blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_by_ai = models.BooleanField(default=True)

    def __str__(self):
        if self.category:
            return f"{self.category.name} - {self.name}"
        return self.name

    class Meta:
        ordering = ['name']
        unique_together = ('user', 'category', 'name')


# ==============================
# QUIZ MODEL
# ==============================
class Quiz(models.Model):
    DIFFICULTY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    category = models.ForeignKey(QuizCategory, on_delete=models.CASCADE, related_name="quizzes")
    subcategory = models.ForeignKey(QuizSubcategory, on_delete=models.CASCADE, related_name="quizzes", blank=True, null=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="easy")
    created_by_ai = models.BooleanField(default=True)
    date_taken = models.DateTimeField(auto_now_add=True)

    # Dynamic time limit (auto-set based on number of questions)
    time_limit = models.IntegerField(default=300)  # fallback default (in seconds)

    def set_dynamic_time(self, num_questions):
        """Automatically assign time = 60 seconds per question."""
        self.time_limit = num_questions * 60
        self.save()

    def __str__(self):
        return f"{self.title} ({self.difficulty})"


# ==============================
# QUESTION MODEL
# ==============================
class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions", null=True, blank=True)
    text = models.TextField()
    options = models.JSONField(default=list)  # e.g. ["A", "B", "C", "D"]
    correct_answer = models.CharField(max_length=200)
    explanation = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Q: {self.text[:60]}..."

    def get_option_labels(self):
        """Return labeled options (A, B, C...)"""
        return [f"{chr(65 + i)}. {opt}" for i, opt in enumerate(self.options)]


# ==============================
# QUIZ HISTORY MODEL
# ==============================
class QuizHistory(models.Model):
    DIFFICULTY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts", null=True, blank=True)

    # ✅ For mixed-category quiz, store multiple categories/subcategories as JSON
    categories_selected = models.JSONField(default=list, blank=True, null=True)
    subcategories_selected = models.JSONField(default=list, blank=True, null=True)

    # For regular single-category quiz
    category = models.CharField(max_length=100, blank=True, null=True)
    subcategory = models.CharField(max_length=100, blank=True, null=True)

    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="easy")
    score = models.IntegerField(default=0)
    score_percentage = models.FloatField(blank=True, null=True)
    total_questions = models.IntegerField(default=0)
    completed = models.BooleanField(default=False)
    date_taken = models.DateTimeField(auto_now_add=True)
    start_time = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict)  # e.g. {"Q1": "A", "Q2": "B"}

    # Dynamic time stored with each attempt
    time_limit = models.IntegerField(default=300)

    class Meta:
        verbose_name = "Quiz History"
        verbose_name_plural = "Quiz Histories"
        ordering = ['-date_taken']

    def __str__(self):
        if self.categories_selected:
            cats = ", ".join([c for c in self.categories_selected])
            return f"{self.user.username} - Mixed ({cats}) [{self.difficulty}]"
        return f"{self.user.username} - {self.category} ({self.difficulty}) - {self.score}/{self.total_questions}"

    @property
    def percentage(self):
        """Return score percentage."""
        if self.total_questions > 0:
            return round((self.score / self.total_questions) * 100, 2)
        return 0

    def set_time_limit(self, num_questions):
        """Set dynamic time based on number of questions (60s per question)."""
        self.time_limit = num_questions * 60
        self.save()


# ==============================
# BADGE SYSTEM
# ==============================
class Badge(models.Model):
    TIER_CHOICES = [
        ('bronze', '🥉 Bronze'),
        ('silver', '🥈 Silver'),
        ('gold', '🥇 Gold'),
    ]

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    icon = models.ImageField(upload_to='badges/', blank=True, null=True)
    criteria = models.CharField(max_length=255, help_text="Condition for earning badge (e.g., 'score>=80', 'completed_10_quizzes')")
    tier = models.CharField(max_length=10, choices=TIER_CHOICES, default='bronze')

    def __str__(self):
        return f"{self.name} ({self.get_tier_display()})"


class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'badge')

    def __str__(self):
        return f"{self.user.username} - {self.badge.name}"
