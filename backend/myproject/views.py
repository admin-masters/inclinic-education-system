from django.shortcuts import render, redirect


def home_view(request):
    """
    Landing page that shows home.html for unauthenticated users 
    and redirects to manage data panel after login.
    """
    if request.user.is_authenticated:
        return redirect('manage_data_panel')
    return render(request, 'home.html')
