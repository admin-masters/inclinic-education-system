# shortlink_management/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, DeleteView
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse

from .models import ShortLink
from .forms import ShortLinkForm
from .decorators import admin_required
from collateral_management.models import Collateral


# ----------------------------------------------------------------
# List Short Links
# ----------------------------------------------------------------
class ShortLinkListView(ListView):
    model = ShortLink
    template_name = 'shortlink_management/shortlink_list.html'
    context_object_name = 'shortlinks'
    ordering = ['-date_created']


# ----------------------------------------------------------------
# Detail Short Link
# ----------------------------------------------------------------
class ShortLinkDetailView(DetailView):
    model = ShortLink
    template_name = 'shortlink_management/shortlink_detail.html'
    context_object_name = 'shortlink'


# ----------------------------------------------------------------
# Create Short Link (Admin Only)
# ----------------------------------------------------------------
@admin_required
def create_short_link(request):
    """
    Allows an admin to pick a Collateral, optionally override short_code,
    and store it in the ShortLink table with resource_type='collateral'.
    """
    if request.method == 'POST':
        form = ShortLinkForm(request.POST)
        if form.is_valid():
            collateral = form.cleaned_data['collateral']
            short_code = form.cleaned_data['short_code']

            shortlink = form.save(commit=False)
            shortlink.resource_type = 'collateral'
            shortlink.resource_id = collateral.id
            shortlink.created_by = request.user
            shortlink.date_created = timezone.now()
            shortlink.save()

            messages.success(request, f"Short link created: {shortlink.short_code}")
            return redirect('shortlink_list')
    else:
        form = ShortLinkForm()
    return render(request, 'shortlink_management/shortlink_create.html', {'form': form})


# ----------------------------------------------------------------
# Delete Short Link (Admin Only)
# ----------------------------------------------------------------
@method_decorator(admin_required, name='dispatch')
class ShortLinkDeleteView(DeleteView):
    model = ShortLink
    template_name = 'shortlink_management/shortlink_delete.html'
    success_url = reverse_lazy('shortlink_list')


# ----------------------------------------------------------------
# Resolve Short Link
# ----------------------------------------------------------------
def resolve_shortlink(request, code):
    """
    Resolve the short code and redirect to the doctor verification page (WhatsApp number verification).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    shortlink = get_object_or_404(ShortLink, short_code=code, is_active=True)
    logger.info(f"Found shortlink: {shortlink}")
    
    collateral = shortlink.get_collateral()
    logger.info(f"Found collateral: {collateral}")
    logger.info(f"Collateral is_active: {collateral.is_active if collateral else 'No collateral'}")

    if collateral:
        # Redirect to doctor verification page with short_link_id as query param
        from django.urls import reverse
        from django.conf import settings
        
        # Use the proper domain for production redirect
        if hasattr(settings, 'SHORTLINK_REDIRECT_DOMAIN') and settings.SHORTLINK_REDIRECT_DOMAIN and not settings.DEBUG:
            base_url = settings.SHORTLINK_REDIRECT_DOMAIN
        else:
            # Fallback to current request domain (for development)
            base_url = f"{request.scheme}://{request.get_host()}"
        
        verify_url = f"{base_url}/view/collateral/verify/?short_link_id={shortlink.id}"
        logger.info(f"Redirecting to: {verify_url}")
        return redirect(verify_url)
    else:
        logger.warning(f"Redirect condition failed - collateral: {collateral}")

    messages.error(request, "Resource not found or inactive.")
    return render(
        request,
        "shortlink_management/resolve_shortlink.html",
        {"shortlink": shortlink, "collateral": collateral},
    )


def debug_shortlink(request, code):
    """
    Debug function to check shortlink details
    """
    try:
        shortlink = ShortLink.objects.get(short_code=code)
        collateral = shortlink.get_collateral()
        
        debug_info = {
            'shortlink_id': shortlink.id,
            'short_code': shortlink.short_code,
            'is_active': shortlink.is_active,
            'resource_type': shortlink.resource_type,
            'resource_id': shortlink.resource_id,
            'collateral': {
                'id': collateral.id if collateral else None,
                'title': collateral.title if collateral else None,
                'is_active': collateral.is_active if collateral else None,
            } if collateral else None,
            'redirect_url': f"/view/collateral/verify/?short_link_id={shortlink.id}"
        }
        
        return JsonResponse(debug_info)
    except ShortLink.DoesNotExist:
        return JsonResponse({'error': 'Shortlink not found'}, status=404)
