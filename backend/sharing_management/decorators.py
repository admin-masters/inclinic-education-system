from django.shortcuts import redirect
from django.contrib import messages

def field_rep_required(view_func):
    """
    Decorator to ensure only 'field_rep' users can access the view.
    """
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and user.role == 'field_rep':
            return view_func(request, *args, **kwargs)
        else:
            return redirect('share_logs')  # or some other page
    return _wrapped_view
