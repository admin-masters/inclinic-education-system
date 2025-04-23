from django.shortcuts import render, redirect

def home_view(request):
    """
    Landing page that redirects users based on their role
    """
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            return redirect('admin_dashboard:dashboard')
        else:  # field_rep
            return redirect('fieldrep_dashboard')
    else:
        # Show a public landing page for unauthenticated users
        return render(request, 'home.html')
