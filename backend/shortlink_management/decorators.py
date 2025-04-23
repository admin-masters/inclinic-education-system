# shortlink_management/decorators.py
from django.shortcuts import redirect
from django.contrib import messages

def admin_required(view_func):
    """
    Decorator to ensure only 'admin' users can access the view.
    """
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and user.role == 'admin':
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "You do not have permission to access this page.")
            return redirect('shortlink_list')
    return _wrapped_view