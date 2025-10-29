from django.contrib import admin
import json
from django.utils.safestring import mark_safe

from .models import (
    Profile,
    QuizCategory,
    QuizSubcategory,
    Quiz,
    Question,
    QuizHistory,
)


# --------------------
# Profile Admin
# --------------------
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'get_first_name', 'get_last_name',
        'gender', 'location', 'dob', 'preferences', 'avatar'
    )
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'location')
    list_filter = ('gender',)

    def get_first_name(self, obj):
        return obj.user.first_name
    get_first_name.short_description = 'First Name'

    def get_last_name(self, obj):
        return obj.user.last_name
    get_last_name.short_description = 'Last Name'


@admin.register(QuizCategory)
class QuizCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

@admin.register(QuizSubcategory)
class QuizSubcategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name", "category__name")

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "subcategory", "difficulty", "date_taken")
    search_fields = ("title", "category__name", "subcategory__name")
    list_filter = ("difficulty", "category", "date_taken")

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("short_text", "quiz", "correct_answer")
    search_fields = ("text", "quiz__title")
    list_filter = ("quiz",)

    def short_text(self, obj):
        return obj.text[:70] + ("..." if len(obj.text) > 70 else "")
    short_text.short_description = "Question"


@admin.register(QuizHistory)
class QuizHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "quiz",
        "score",
        "total_questions",
        "score_percentage",
        "date_taken",
        "difficulty",
          # only in list view
    )
    search_fields = ("user__username", "quiz__title")
    list_filter = ("date_taken",)
    readonly_fields = ("date_taken", "formatted_answers")
    
    # ✅ Exclude the raw 'answers' JSON field
    exclude = ("answers",)

    def formatted_answers(self, obj):
        if not obj.answers:
            return "-"
        pretty_json = json.dumps(obj.answers, indent=2, ensure_ascii=False)
        return mark_safe(f"<pre>{pretty_json}</pre>")
    formatted_answers.short_description = "Answers"


