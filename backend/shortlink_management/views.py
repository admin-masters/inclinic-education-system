# shortlink_management/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, DeleteView
from django.contrib import messages

from .models import ShortLink
from .forms import ShortLinkForm
from .decorators import admin_required
from collateral_management.models import Collateral

from django.utils import timezone


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
# This is what doctors/others might click in real usage:
# e.g. /short/<short_code> -> redirect or display resource
# ----------------------------------------------------------------
def resolve_shortlink(request, code):
    """
    1. Look up the short link by short_code.
    2. If found & active, fetch the resource (Collateral).
    3. (In a real app, you'd redirect or show a PDF/video viewer.)
    """
    shortlink = get_object_or_404(ShortLink, short_code=code, is_active=True)
    collateral = shortlink.get_collateral()

    if not collateral:
        messages.error(request, "Resource not found or invalid.")
        return redirect('shortlink_list')

    # For demonstration, let's just display a simple page with collateral info
    return render(request, 'shortlink_management/resolve_shortlink.html', {
        'shortlink': shortlink,
        'collateral': collateral,
    })