"""
URL configuration for myproject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from .views import home_view
from django.views.generic import RedirectView
from django.contrib.auth import views as auth_views
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [
    path('', home_view, name='home'),
    path('admin/', admin.site.urls),
    path('auth/', include('social_django.urls', namespace='social')),
    path('collaterals/', include('collateral_management.urls')),
    path('user/', include('user_management.urls')),
    path('campaigns/', include('campaign_management.urls')),
    path('share/', include('sharing_management.urls')),
    path('view/', include('doctor_viewer.urls')),
    path('api/', include('api.api_urls')),   
    # path('admin/dashboard/', include('admin_dashboard.urls', namespace='admin_dashboard')),
    path('admin-dashboard/', include(('admin_dashboard.urls', 'admin_dashboard'), namespace='admin-dashboard')),
    path('auth/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('shortlinks/', include('shortlink_management.urls')),
    
    # Custom admin login redirect to field reps
    path('admin/login/', auth_views.LoginView.as_view(
        template_name='admin/login.html',
        redirect_field_name='next',
        success_url='/admin-dashboard/fieldreps/'
    ), name='admin_login'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
