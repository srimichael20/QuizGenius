from django.db import models
from ..models import Badge, UserBadge, QuizHistory
from django.utils import timezone

def check_and_award_badges(user):
    """Check quiz stats and award new badges dynamically."""
    completed_quizzes = QuizHistory.objects.filter(user=user, completed=True)
    score_avg = completed_quizzes.aggregate(avg=models.Avg('score_percentage'))['avg'] or 0
    total_quizzes = completed_quizzes.count()

    # --- Badge Conditions ---
    conditions = [
        {
            "name": "First Quiz Completed",
            "desc": "Completed your first quiz.",
            "tier": "bronze",
            "criteria": total_quizzes >= 1
        },
        {
            "name": "Quiz Explorer",
            "desc": "Completed 5 quizzes!",
            "tier": "silver",
            "criteria": total_quizzes >= 5
        },
        {
            "name": "Quiz Master",
            "desc": "Completed 10 quizzes!",
            "tier": "gold",
            "criteria": total_quizzes >= 10
        },
        {
            "name": "High Achiever",
            "desc": "Scored above 90% in any quiz.",
            "tier": "silver",
            "criteria": completed_quizzes.filter(score_percentage__gte=90).exists()
        },
        {
            "name": "Consistency King",
            "desc": "Average score above 80%.",
            "tier": "gold",
            "criteria": score_avg >= 80
        },
    ]

    awarded = []

    for c in conditions:
        badge, _ = Badge.objects.get_or_create(
            name=c["name"],
            defaults={
                "description": c["desc"],
                "criteria": c["name"].lower().replace(" ", "_"),
                "tier": c["tier"],
            }
        )

        if c["criteria"] and not UserBadge.objects.filter(user=user, badge=badge).exists():
            UserBadge.objects.create(user=user, badge=badge, earned_at=timezone.now())
            awarded.append(badge)

    return awarded
