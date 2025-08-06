# shortlink_management/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, DeleteView
from django.contrib import messages
from django.utils import timezone

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
    shortlink = get_object_or_404(ShortLink, short_code=code, is_active=True)
    collateral = shortlink.get_collateral()

    if collateral and collateral.is_active:
        # Redirect to doctor verification page with short_link_id as query param
        from django.urls import reverse
        verify_url = reverse("doctor_collateral_verify") + f"?short_link_id={shortlink.id}"
        return redirect(verify_url)

    messages.error(request, "Resource not found or inactive.")
    return render(
        request,
        "shortlink_management/resolve_shortlink.html",
        {"shortlink": shortlink, "collateral": collateral},
    )
