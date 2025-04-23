# campaign_management/decorators.py
from django.shortcuts import redirect
from django.contrib import messages

def admin_required(view_func):
    """
    Decorator to ensure only 'admin' users can access the view.
    """
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == 'admin':
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "You do not have permission to view this page.")
            return redirect('campaign_list')  # or some other page
    return _wrapped_view