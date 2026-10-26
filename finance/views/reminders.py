from django.http import Http404
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from finance.models import UserProfile
from finance.reminders import user_from_token


@csrf_exempt  # authenticated by the signed token; mail clients send one-click unsubscribe as a bare POST
def reminder_unsubscribe(request, token):
    user = user_from_token(token)
    if user is None:
        raise Http404
    profile, _ = UserProfile.objects.get_or_create(user=user)
    done = False
    if request.method == "POST":
        UserProfile.objects.filter(pk=profile.pk).update(reminder_emails=False)
        done = True
    return render(request, "reminder_unsubscribe.html", {
        "done": done,
        "is_lt": (profile.preferred_language or "lt") != "en",
    })
