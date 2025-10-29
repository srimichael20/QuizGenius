from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.contrib.auth.views import LoginView, LogoutView
from django.templatetags.static import static
import datetime
from datetime import timedelta
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm, QuizStartForm
from .models import Profile, QuizCategory, QuizSubcategory, QuizHistory, Quiz, Badge, UserBadge
from .utils.badges import check_and_award_badges
from django.http import JsonResponse
from django.db.models import Sum, Count 
import re 
from openai import OpenAI
#import google.generativeai as genai
from django.conf import settings

#genai.configure(api_key=settings.GEMINI_API_KEY)
OPENAI_CLIENT = OpenAI(api_key=settings.OPENAI_API_KEY)
#model = genai.GenerativeModel("gemini-1.5-flash")

# ------------------ User Authentication ------------------ #


def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            Profile.objects.get_or_create(user=user)  # auto-create profile
            login(request, user)
            messages.success(request, "🎉 Your account has been created!")
            return redirect('home')
    else:
        form = UserRegisterForm()
    return render(request, 'users/register.html', {'form': form})


class CustomLoginView(LoginView):
    template_name = 'users/login.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        Profile.objects.get_or_create(user=self.request.user)  # ensure profile exists
        return response


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('login')

    def dispatch(self, request, *args, **kwargs):
        messages.success(request, "✅ You have been logged out successfully!")
        return super().dispatch(request, *args, **kwargs)


# ------------------ Profile ------------------ #
@login_required
def profile(request):
    user = request.user

    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=user.profile)

        if u_form.is_valid() and p_form.is_valid():
            # Save first_name and last_name
            u_form.save()

            # Save profile fields
            profile = p_form.save(commit=False)
            
            # Update preferences from hidden input
            preferences_input = request.POST.get('preferences', '')
            profile.preferences = ",".join([p.strip() for p in preferences_input.split(",") if p.strip()])
            if 'avatar' in request.FILES:
                profile.avatar = request.FILES['avatar']
            profile.save()

            messages.success(request, "✅ Profile updated successfully!")
            return redirect('profile')
        else:
            messages.error(request, "❌ Please correct the errors below.")
            # For debugging (optional, remove in production)
            print("User form errors:", u_form.errors)
            print("Profile form errors:", p_form.errors)

    else:
        u_form = UserUpdateForm(instance=user)
        p_form = ProfileUpdateForm(instance=user.profile)

    # Convert preferences string to list for display
    preferences_list = []
    if user.profile.preferences:
        preferences_list = [p.strip() for p in user.profile.preferences.split(',') if p.strip()]

    context = {
        'u_form': u_form,
        'p_form': p_form,
        'preferences_list': preferences_list,
        'avatar_default': static("avatars/default_avatar.png"),
    }

    return render(request, 'users/profile.html', context)

@login_required
def update_theme(request):
    if request.method == "POST":
        theme = request.POST.get("theme")
        profile = request.user.profile
        if theme in dict(profile.THEME_CHOICES).keys():
            profile.theme = theme
            profile.save()
    return redirect(request.META.get('HTTP_REFERER', 'home')) 

# ------------------ Start Quiz ------------------ #
@login_required
def start_quiz(request, quiz_id=None):
    """
    Start a new quiz or resume incomplete quiz if quiz_id provided.
    """
    categories = QuizCategory.objects.all().order_by('name')
    form = QuizStartForm(request.POST or None)
    CATEGORY_SETTINGS = {
        "academics": {"system_prompt": "Strict academic quiz generator.", "temperature": 0.0},
        "entertainment": {"system_prompt": "Creative entertainment quiz generator.", "temperature": 0.4},
        "general": {"system_prompt": "General knowledge quiz generator.", "temperature": 0.3},
    }
    MAX_MIX_CATEGORIES = 5

    # ================== Resume Incomplete Quiz ==================
    if quiz_id:
        history = get_object_or_404(QuizHistory, id=quiz_id, user=request.user, completed=False)
        # Restore session data from history
        request.session.update({
            "quiz_questions": [v for k, v in (history.answers or {}).items()],
            "quiz_answers": {str(i+1): v.get("correct_answer", "A") for i, v in enumerate(history.answers.values())},
            "quiz_category": history.category,
            "quiz_category_id": None,
            "quiz_subcategory": history.subcategory,
            "quiz_subcategory_id": None,
            "quiz_difficulty": history.difficulty,
            "quiz_start_time": timezone.now().isoformat(),  # reset timer on resume
            "quiz_time_limit": history.time_limit or 300,
            "quiz_history_id": history.id,
        })
        return redirect("take_quiz", quiz_id=history.id)

    # ================== Handle POST (New Quiz Generation) ==================
    if request.method == "POST" and form.is_valid():
        try:
            num_questions = int(form.cleaned_data.get("question_count", 10))
            if num_questions <= 0:
                raise ValueError()
        except Exception:
            messages.error(request, "Please select a valid number of questions.")
            return render(request, "users/start_quiz.html", {"form": form, "categories": categories})

        difficulty = form.cleaned_data.get("difficulty", "easy")
        total_time = num_questions * 60  # seconds per question

       # ----------------- Mixed Quiz -----------------
        multi_categories = request.POST.getlist("category_choices_multi")
        if multi_categories:
            if len(multi_categories) > MAX_MIX_CATEGORIES:
                messages.error(request, f"Select up to {MAX_MIX_CATEGORIES} categories.")
                return render(request, "users/start_quiz.html", {"form": form, "categories": categories})

            selected_categories = QuizCategory.objects.filter(id__in=multi_categories)
            if not selected_categories.exists():
                messages.error(request, "Please select at least one valid category.")
                return render(request, "users/start_quiz.html", {"form": form, "categories": categories})

            category_names = [c.name for c in selected_categories]

            system_prompt = (
                "You are an expert quiz generator. Generate high-quality multiple-choice questions (MCQs). "
                "Each question must have 4 options labeled (A), (B), (C), (D). "
                "Do NOT include category names in the question text. "
                "Provide an 'Answers:' section at the end with only the correct option letters."
            )

            # Strictly formatted user prompt
            user_prompt = (
                f"Generate exactly {num_questions} MCQ questions on: {', '.join(category_names)}.\n"
                f"Difficulty: {difficulty}.\n"
                "Format:\n"
                "Q1. Question text\nA) Option 1\nB) Option 2\nC) Option 3\nD) Option 4\n"
                "Q2. Question text\nA) Option 1\nB) Option 2\nC) Option 3\nD) Option 4\n"
                "...\n"
                "Answers:\n1) A\n2) B\n3) C\n... (only letters, one per line matching each question)"
            )

            try:
                response = OPENAI_CLIENT.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                )

                ai_output = response.choices[0].message.content.strip()
                parsed = parse_questions(ai_output)

                # Check AI output validity
                if not parsed or not parsed.get("questions"):
                    messages.error(request, "AI did not generate valid questions. Try again.")
                    return render(request, "users/start_quiz.html", {"form": form, "categories": categories})

                questions = parsed.get("questions", [])[:num_questions]
                answers = {str(k): v for k, v in parsed.get("answers", {}).items()}

                for idx, q in enumerate(questions, start=1):
                    q["id"] = str(idx)
                    correct_letter = answers.get(str(idx), "A").upper()
                    full_text = next((opt for opt in q["options"] if opt.startswith(correct_letter)), "")
                    q["correct_answer"] = full_text or f"{correct_letter})"

                category_names = [c.name for c in selected_categories]
                print("Selected categories for mixed quiz:", category_names)
                # Save quiz history
                quiz_history = QuizHistory.objects.create(
                    user=request.user,
                    category="Mixed Quiz",
                    subcategory="",
                    difficulty=difficulty,
                    total_questions=num_questions,
                    time_limit=total_time,
                    categories_selected=category_names,
                    answers={str(idx): {"question": q["question"], "options": q["options"], "correct_answer": q["correct_answer"]}
                            for idx, q in enumerate(questions, start=1)},
                    completed=False
                )

                # Save quiz in session
                request.session.update({
                    "quiz_questions": questions,
                    "quiz_answers": answers,
                    "quiz_category": "Mixed Quiz",
                    "quiz_category_id": None,
                    "quiz_subcategory": "",
                    "quiz_subcategory_id": None,
                    "quiz_difficulty": difficulty,
                    "quiz_start_time": timezone.now().isoformat(),
                    "quiz_time_limit": total_time,
                    "quiz_history_id": quiz_history.id,
                })

                messages.success(request, f"✅ Mixed Quiz generated with {len(questions)} questions.")
                return redirect("take_quiz", quiz_id=quiz_history.id)

            except Exception as e:
                messages.error(request, f"❌ Mixed quiz generation failed: {str(e)}")
                return render(request, "users/start_quiz.html", {"form": form, "categories": categories})


        # ----------------- Single Category -----------------
        category = form.cleaned_data.get("category")
        subcategory = form.cleaned_data.get("subcategory")

        if not category:
            messages.error(request, "Please select a valid category or choose Mixed Quiz mode.")
            return render(request, "users/start_quiz.html", {"form": form, "categories": categories})

        category_key = (category.name or "").lower()
        settings = CATEGORY_SETTINGS.get(category_key, CATEGORY_SETTINGS["general"])
        topic = f"{subcategory.name if subcategory else category.name} ({difficulty})"

        user_prompt = (
            f"Generate exactly {num_questions} MCQ questions on {topic}. "
            "Each must have 4 options (A, B, C, D) and an 'Answers:' section at the end."
        )

        try:
            response = OPENAI_CLIENT.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": settings["system_prompt"]},
                        {"role": "user", "content": user_prompt}],
                temperature=settings["temperature"],
            )

            ai_output = response.choices[0].message.content.strip()
            parsed = parse_questions(ai_output)
            questions = parsed["questions"][:num_questions]
            answers = {str(k): v for k, v in parsed["answers"].items()}

            for idx, q in enumerate(questions, start=1):
                q["id"] = str(idx)
                correct_letter = answers.get(str(idx), "A").upper()
                full_text = next((opt for opt in q["options"] if opt.startswith(correct_letter)), "")
                q["correct_answer"] = full_text or f"{correct_letter})"

            # Create QuizHistory for this attempt
            quiz_history = QuizHistory.objects.create(
                user=request.user,
                category=category.name,
                subcategory=subcategory.name if subcategory else "",
                difficulty=difficulty,
                total_questions=num_questions,
                time_limit=total_time,
                answers={str(idx): {"question": q["question"], "options": q["options"], "correct_answer": q["correct_answer"]} for idx, q in enumerate(questions, start=1)},
                completed=False
            )

            request.session.update({
                "quiz_questions": questions,
                "quiz_answers": answers,
                "quiz_category": category.name,
                "quiz_category_id": category.id,
                "quiz_subcategory": subcategory.name if subcategory else "",
                "quiz_subcategory_id": subcategory.id if subcategory else None,
                "quiz_difficulty": difficulty,
                "quiz_start_time": timezone.now().isoformat(),
                "quiz_time_limit": total_time,
                "quiz_history_id": quiz_history.id,
            })

            messages.success(request, f"✅ {len(questions)} questions generated successfully.")
            return redirect("take_quiz", quiz_id=quiz_history.id)

        except Exception as e:
            messages.error(request, f"❌ Quiz generation failed: {e}")
            return render(request, "users/start_quiz.html", {"form": form, "categories": categories})

    # Render form for GET or invalid POST
    return render(request, "users/start_quiz.html", {"form": form, "categories": categories})



# ------------------ Take Quiz ------------------ #
@login_required
def take_quiz(request, quiz_id):
    """
    Take or resume a quiz with server-side time validation.
    """
    quiz_history = get_object_or_404(QuizHistory, id=quiz_id, user=request.user)
    questions = [v for k, v in (quiz_history.answers or {}).items()]
    
    if not questions:
        messages.warning(request, "⚠ No quiz found. Please start again.")
        return redirect("start_quiz")

    # Timer setup
    time_limit = quiz_history.time_limit or 300  # default 5 minutes
    start_time = quiz_history.start_time
    if not start_time:
        start_time = timezone.now()
        quiz_history.start_time = start_time
        quiz_history.save()

    elapsed = (timezone.now() - start_time).total_seconds()
    time_left = max(int(time_limit - elapsed), 0)

    # Normalize options
    for q in questions:
        if isinstance(q.get("options"), str):
            q["options"] = [opt.strip() for opt in re.split(r"[;,\n]+", q["options"]) if opt.strip()]
        elif not isinstance(q.get("options"), list):
            q["options"] = list(q.get("options", []))

    # Store questions in session for client-side use
    request.session["quiz_questions"] = questions

    return render(
        request,
        "users/take_quiz.html",
        {"questions": questions, "time_left": time_left, "quiz_id": quiz_id},
    )


# ------------------ Save Answer AJAX ------------------ #
@login_required
@require_POST
def save_answer_ajax(request):
    """
    AJAX endpoint to save user answer in real-time.
    """
    quiz_id = request.POST.get("quiz_id")
    qid = request.POST.get("question_id")
    answer = request.POST.get("answer")

    quiz_history = get_object_or_404(QuizHistory, id=quiz_id, user=request.user)

    # Check server-side timer to prevent cheating
    if quiz_history.start_time:
        elapsed = (timezone.now() - quiz_history.start_time).total_seconds()
        if quiz_history.time_limit and elapsed > quiz_history.time_limit:
            return JsonResponse({"status": "error", "message": "Time is over!"})

    answers = quiz_history.answers or {}
    if qid in answers:
        answers[qid]["user_answer"] = answer
        answers[qid]["last_saved"] = timezone.now().isoformat()  # autosave timestamp
    else:
        answers[qid] = {"user_answer": answer, "last_saved": timezone.now().isoformat()}

    quiz_history.answers = answers
    quiz_history.save()
    return JsonResponse({"status": "success"})



# ------------------ Submit Quiz ------------------ #
@login_required
def submit_quiz(request, quiz_id):

    """
    Submit the quiz, calculate score, handle autosaved answers, and cleanup.
    """

    history = get_object_or_404(QuizHistory, id=quiz_id, user=request.user)
    questions = request.session.get("quiz_questions", [])
    correct_answers = request.session.get("quiz_answers", {})

    if not questions or not correct_answers:
        messages.warning(request, "⚠ No quiz found. Please start a new quiz.")
        return redirect("start_quiz")

    # Merge autosaved answers from database
    saved_answers = history.answers or {}
    
    # Calculate score
    score = 0
    results = []
    for idx, q in enumerate(questions, start=1):
        qid = str(idx)
        # Prefer AJAX saved answer, fallback to POST
        user_ans = saved_answers.get(qid, {}).get("user_answer") or request.POST.get(f"q{qid}", "").strip()
        correct_letter = str(correct_answers.get(qid, "A")).upper()

        # Map user answer and correct answer to full option text
        user_full = next((opt for opt in q.get("options", []) if opt.startswith(user_ans.upper())), user_ans)
        correct_full = next((opt for opt in q.get("options", []) if opt.startswith(correct_letter)), correct_letter)

        # Determine correctness
        is_correct = user_full.startswith(correct_full.split(")")[0]) if user_full and correct_full else False
        if is_correct:
            score += 1

        explanation = ""
        if not is_correct:
            explanation = get_explanation(q["question"], correct_full, user_full)

        results.append({
            "id": qid,
            "question": q.get("question"),
            "user_answer": user_full or "Not answered",
            "correct_answer": correct_full,
            "is_correct": is_correct,
            "explanation": explanation,
            "options": q.get("options", []),
        })

    total_questions = len(questions)
    score_percentage = round((score / total_questions) * 100, 2) if total_questions else 0

    # Save results
    history.answers = {r["id"]: r for r in results}
    history.score = score
    history.score_percentage = score_percentage
    history.completed = True
    history.completed_at = timezone.now()
    history.save()

    new_badges = check_and_award_badges(request.user)
    if new_badges:
        names = ", ".join([b.name for b in new_badges])
        messages.success(request, f"🏅 You earned new badges: {names}!")

    # Cleanup session
    session_keys = [
        "quiz_questions", "quiz_answers", "quiz_category", "quiz_category_id",
        "quiz_subcategory", "quiz_subcategory_id", "quiz_difficulty",
        "quiz_start_time", "quiz_time_limit", "quiz_history_id"
    ]
    for key in session_keys:
        request.session.pop(key, None)

    messages.success(request, f"✅ Quiz submitted! You scored {score}/{total_questions} ({score_percentage}%).")
    return redirect("quiz_result", quiz_id=history.id)


# ------------------ Quiz Result ------------------ #
@login_required
def quiz_result(request, quiz_id):
    try:
        #history = QuizHistory.objects.get(id=quiz_id, user=request.user)
        history = get_object_or_404(QuizHistory, id=quiz_id, user=request.user)
    except QuizHistory.DoesNotExist:
        messages.warning(request, "⚠ Quiz not found.")
        return redirect("dashboard")

    results = []
    for qid, data in (history.answers or {}).items():
        results.append({
            "id": qid,
            "question": data.get("question", ""),
            "user_answer": data.get("user_answer", ""),
            "correct_answer": data.get("correct_answer", ""),
            "explanation": data.get("explanation", ""),
            "is_correct": data.get("is_correct", False),
            "options": data.get("options", []),
        })

    context = {
        "score": history.score,
        "total": history.total_questions,
        "score_percentage": history.score_percentage,
        "results": results,
    }

    return render(request, "users/quiz_result.html", context)


    
# ------------------ Retake Quiz ------------------ #
@login_required
def retake_quiz(request, quiz_id):
    """
    Allows user to retake a previously attempted quiz.
    """
    quiz = get_object_or_404(QuizHistory, id=quiz_id, user=request.user)
    quiz.completed = False
    quiz.save()
    messages.info(request, f"♻️ Retaking quiz: {quiz.category} ({quiz.difficulty})")
    return redirect("start_quiz", quiz_id = quiz.id)

@login_required()
def dashboard(request):
    # Fetch quiz history
    histories = QuizHistory.objects.filter(user=request.user).order_by('-date_taken')
    completed = histories.filter(completed=True)
    incomplete = histories.filter(completed=False)

    # Total score of completed quizzes
    total_score = completed.aggregate(Sum('score'))['score__sum'] or 0

    # ✅ Calculate progress for incomplete quizzes
    incomplete_list = []
    for quiz in incomplete:
        answers = quiz.answers or {}
        # Convert JSON string to dict if needed
        if isinstance(answers, str):
            try:
                answers = json.loads(answers)
            except json.JSONDecodeError:
                answers = {}
        answered_count = sum(1 for v in answers.values() if v.get("user_answer"))
        total = quiz.total_questions or 1  # avoid division by zero
        quiz.progress = int((answered_count / total) * 100)
        incomplete_list.append(quiz)

    completed_list = list(completed) 
    # Set subcategory_display for all quizzes
    for quiz in incomplete_list + completed_list:
        if quiz.category == "Mixed Quiz":
            # Use categories_selected JSONField
            if quiz.categories_selected:
                quiz.subcategory_display = ", ".join(quiz.categories_selected)
            else:
                quiz.subcategory_display = "Multiple Categories"
        else:
            quiz.subcategory_display = quiz.subcategory  # normal quizzes


    # ✅ Leaderboard (Top 10)
    rankings = (
        QuizHistory.objects.filter(completed=True)
        .values('user__id', 'user__username')
        .annotate(total_score=Sum('score'), quizzes=Count('id'))
        .order_by('-total_score')[:10]
    )

    # 🎯 Badge Progress
    all_badges = Badge.objects.all()
    owned_badge_ids = list(request.user.user_badges.values_list('badge_id', flat=True))
    completed_count = completed.count()

    # Reuse similar progress logic
    badge_progress = {}
    for badge in all_badges:
        progress = 0
        if badge.criteria.startswith("score>="):
            required = int(badge.criteria.split(">=")[1])
            progress = min(int((total_score / required) * 100), 100)
        elif badge.criteria.startswith("completed_"):
            required = int(badge.criteria.split("_")[1])
            progress = min(int((completed_count / required) * 100), 100)
        elif badge.criteria.startswith("streak>="):
            # Fetch streak data from home logic (optional optimization)
            today = timezone.now().date()
            completed_dates = sorted({h.date_taken.date() for h in completed}, reverse=True)
            streak_days = 0
            consecutive_day = today
            for d in completed_dates:
                if d == consecutive_day:
                    streak_days += 1
                    consecutive_day -= timedelta(days=1)
                elif d < consecutive_day:
                    break
            required = int(badge.criteria.split(">=")[1])
            progress = min(int((streak_days / required) * 100), 100)
        badge_progress[badge.id] = progress



    # ✅ Pass all context to template
    context = {
        'completed': completed_list,
        'incomplete': incomplete_list,
        'total_score': total_score,
        'rankings': rankings,
        'all_badges': all_badges,
        'owned_badge_ids': owned_badge_ids,
        'badge_progress': badge_progress,
        'all_badges': Badge.objects.all(),
        'owned_badge_ids': list(request.user.user_badges.values_list('badge_id', flat=True)),
    }

    return render(request, 'users/dashboard.html', context)


# ------------------ Parser ------------------ #
def parse_questions(ai_output):
    questions, answers = [], {}
    current_q = None
    lines = ai_output.splitlines()
    in_answers_section = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^answers?:", line, re.IGNORECASE):
            in_answers_section = True
            continue

        if in_answers_section:
            match = re.match(r"(\d+)[\).:\- ]+\s*([A-Da-d])", line)
            if match:
                q_no, ans = int(match.group(1)), match.group(2).upper()
                answers[q_no] = ans
            continue

        q_match = re.match(r"^(?:Q\s*)?(\d+)[\).:\- ]+\s*(.*)", line)
        if q_match:
            if current_q and current_q.get("question") and current_q.get("options"):
                questions.append(current_q)
            current_q = {"id": int(q_match.group(1)), "question": q_match.group(2).strip(), "options": []}
            continue

        opt_match = re.match(r"^([A-Da-d])[\).:\- ]+\s*(.*)", line)
        if opt_match and current_q:
            label = opt_match.group(1).upper()
            opt_text = opt_match.group(2).strip()
            current_q["options"].append(f"{label}) {opt_text}")

    if current_q and current_q.get("question") and current_q.get("options"):
        questions.append(current_q)

    return {"questions": questions, "answers": answers}

# ------------------ Explanation Generator ------------------ #
def get_explanation(question, correct_answer, user_answer=None):
    """
    Generate explanation only when the user selects a wrong answer.
    Explains why the user's answer is incorrect and why the correct answer is right.
    """
    try:
        question = (question or "").strip()
        correct_answer = (correct_answer or "").strip()
        user_answer = (user_answer or "").strip() if user_answer else None

        # Skip explanation if answer is correct or not provided
        if not user_answer or user_answer == correct_answer:
            return ""

        # GPT prompt
        prompt = (
            f"The student answered '{user_answer}', but the correct answer is '{correct_answer}'. "
            f"Explain briefly (2-3 sentences) why '{user_answer}' is incorrect and why "
            f"'{correct_answer}' is correct for the question: {question}"
        )

        response = OPENAI_CLIENT.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert tutor who explains answers clearly and concisely."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=120,
        )

        # Extract response safely
        text = ""
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                text = choice.message.content
            elif hasattr(choice, "text"):
                text = choice.text

        return text.strip() if text else "Explanation unavailable at the moment."

    except Exception as e:
        print("Explanation generation error:", e)
        return "Explanation unavailable at the moment."

@login_required(login_url='login')
def home(request):
    # Ensure profile exists
    profile, _ = Profile.objects.get_or_create(user=request.user)

    # Fetch quiz data
    histories = QuizHistory.objects.filter(user=request.user, completed=True).order_by('-date_taken')
    completed = histories
    incomplete = QuizHistory.objects.filter(user=request.user, completed=False)
    total_score = completed.aggregate(Sum('score'))['score__sum'] or 0

    # ----- Leaderboard Ranking -----
    rankings = (
        QuizHistory.objects.filter(completed=True)
        .values('user__id', 'user__username')
        .annotate(total_score=Sum('score'))
        .order_by('-total_score')
    )
    leaderboard_list = list(rankings)
    user_rank = next((i + 1 for i, u in enumerate(leaderboard_list) if u['user__id'] == request.user.id), None)

    # ----- Calculate Real Streak -----
    streak_days = 0
    today = timezone.now().date()
    consecutive_day = today
    completed_dates = sorted({h.date_taken.date() for h in completed}, reverse=True)

    for d in completed_dates:
        if d == consecutive_day:
            streak_days += 1
            consecutive_day -= timedelta(days=1)
        elif d < consecutive_day:
            break

    # ----- Last 30 Days Streak Visualization -----
    last_30_days = [(today - timedelta(days=i)) for i in range(29, -1, -1)]
    streak_map = {d: 0 for d in last_30_days}
    for h in completed:
        date = h.date_taken.date()
        if date in streak_map:
            streak_map[date] += 1  # count of quizzes per day

    # ----- Today's Quiz Attempts -----
    todays_attempts = completed.filter(date_taken__date=today).count()

    # 🎯 Calculate badge progress
    all_badges = Badge.objects.all()
    owned_badge_ids = list(request.user.user_badges.values_list('badge_id', flat=True))
    badge_progress = {}

    completed_count = completed.count()
    for badge in all_badges:
        progress = 0

        # Handle different badge criteria patterns
        if badge.criteria.startswith("score>="):
            required = int(badge.criteria.split(">=")[1])
            progress = min(int((total_score / required) * 100), 100)

        elif badge.criteria.startswith("completed_"):
            required = int(badge.criteria.split("_")[1])
            progress = min(int((completed_count / required) * 100), 100)

        elif badge.criteria.startswith("streak>="):
            required = int(badge.criteria.split(">=")[1])
            progress = min(int((streak_days / required) * 100), 100)

        badge_progress[badge.id] = progress

    # ----- Daily AI Tip (cached in Profile) -----
    if profile.ai_tip_date == today and profile.ai_tip_text:
        ai_tip = profile.ai_tip_text
    else:
        try:
            prompt = (
                f"Provide a short motivational message or study tip for a user with "
                f"{streak_days} day streak and {todays_attempts} quiz attempts today. "
                "Keep it concise like a Quotes."
            )
            response = OPENAI_CLIENT.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a friendly quiz coach."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
            )
            ai_tip = response.choices[0].message.content.strip()
            profile.ai_tip_text = ai_tip
            profile.ai_tip_date = today
            profile.save()
        except Exception:
            ai_tip = "Keep pushing! Consistency sharpens your mind."

    return render(request, 'users/home.html', {
        'completed': completed,
        'incomplete': incomplete,
        'total_score': total_score,
        'leaderboard_rank': user_rank,
        'user_id': request.user.id,
        'streak_days': streak_days,
        'streak_map': streak_map,  # pass streak for visualization
        'todays_attempts': todays_attempts,
        'ai_tip': ai_tip,
        'rankings': rankings,
        'all_badges': Badge.objects.all(),
        'all_badges': all_badges,
        'owned_badge_ids': owned_badge_ids,
        'badge_progress': badge_progress,
        'owned_badge_ids': list(request.user.user_badges.values_list('badge_id', flat=True)),
    })



@login_required
def category_suggestions(request):
    q = request.GET.get("q", "").strip().lower()

    # Fetch profile preferences
    profile = request.user.profile
    pref_list = []
    if profile.preferences:
        pref_list = [p.strip() for p in profile.preferences.split(",")]

    # Fetch saved categories from DB
    categories = QuizCategory.objects.filter(
        user=request.user, name__icontains=q
    ).values_list("name", flat=True)

    # Merge both (avoid duplicates)
    suggestions = list(set(pref_list + list(categories)))

    # Filter by query
    suggestions = [s for s in suggestions if q in s.lower()]

    return JsonResponse(suggestions, safe=False)


@login_required
def subcategory_suggestions(request):
    """
    Return subcategories for a given category (ID) filtered by optional search query.
    """
    category_id = request.GET.get("category_id")
    query = request.GET.get("q", "").strip().lower()

    subcategories = QuizSubcategory.objects.all()
    if category_id:
        subcategories = subcategories.filter(category_id=category_id)
    if query:
        subcategories = subcategories.filter(name__icontains=query)

    subcategories = subcategories.values("id", "name")
    return JsonResponse(list(subcategories), safe=False)