from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # login & register
    path('', views.CustomLoginView.as_view(), name='login'), 
    path('register/', views.register, name='register'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path("quiz/category-suggestions/", views.category_suggestions, name="category_suggestions"),
    path("quiz/subcategory-suggestions/", views.subcategory_suggestions, name="subcategory_suggestions"),
    path("quiz/start/", views.start_quiz, name="start_quiz"),
    path("quiz/start/<int:quiz_id>/", views.start_quiz, name="start_quiz"),
    path('quiz/take/<int:quiz_id>/', views.take_quiz, name='take_quiz'),
    path('quiz/submit/<int:quiz_id>/', views.submit_quiz, name='submit_quiz'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('quiz/result/<int:quiz_id>/', views.quiz_result, name='quiz_result'),
    path('quiz/retake/<int:quiz_id>/', views.retake_quiz, name='retake_quiz'),
    path('quiz/save_answer/', views.save_answer_ajax, name='save_answer_ajax'),
    path('ajax/subcategories/', views.subcategory_suggestions, name='ajax_subcategories'),
    path('update-theme/', views.update_theme, name='update_theme'),
    path('profile/', views.profile, name='profile'),
    path('home/', views.home, name='home'),

    # optional: password reset
#     path('password-reset/', 
#          auth_views.PasswordResetView.as_view(template_name='users/password_reset.html'), 
#          name='password_reset'),
     path('password-reset/',auth_views.PasswordResetView.as_view(template_name='users/password_reset.html',email_template_name='users/password_reset_email.html',
        extra_email_context={'domain': "127.0.0.1:8000", 'site_name': "Ai_Quiz"}
    ),
    name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='users/password_reset_done.html'), 
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name='users/password_reset_confirm.html'), 
         name='password_reset_confirm'),
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='users/password_reset_complete.html'), 
         name='password_reset_complete'),
]
