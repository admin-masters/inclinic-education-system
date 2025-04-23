from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from utils.recaptcha import recaptcha_required

@login_required
def user_profile(request):
    user = request.user
    data = {
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'active': user.active,
    }
    return JsonResponse(data)

# Example view requiring reCAPTCHA for POST
@login_required
@recaptcha_required
def update_profile(request):
    if request.method == 'POST':
        user = request.user
        email = request.POST.get('email')
        if email:
            user.email = email
            user.save()
            return JsonResponse({'status': 'success', 'message': 'Profile updated'})
    return JsonResponse({'status': 'failed', 'message': 'Invalid request'}, status=400)
