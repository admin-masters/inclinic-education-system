# collateral_management/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages

from .decorators import admin_required
from .models import Collateral, CampaignCollateral
from .forms import CollateralForm, CampaignCollateralForm
from campaign_management.models import Campaign  # reuse your existing Campaign model

# ----------------------------------------------------------------
# Collateral List
# (Optionally open to all roles. You can restrict to admin if needed)
# ----------------------------------------------------------------
class CollateralListView(ListView):
    model = Collateral
    template_name = 'collateral_management/collateral_list.html'
    context_object_name = 'collaterals'
    ordering = ['-created_at']


# ----------------------------------------------------------------
# Collateral Detail
# ----------------------------------------------------------------
class CollateralDetailView(DetailView):
    model = Collateral
    template_name = 'collateral_management/collateral_detail.html'
    context_object_name = 'collateral'


# ----------------------------------------------------------------
# Create Collateral (admin only)
# ----------------------------------------------------------------
@method_decorator(admin_required, name='dispatch')
class CollateralCreateView(CreateView):
    model = Collateral
    form_class = CollateralForm
    template_name = 'collateral_management/collateral_create.html'
    success_url = reverse_lazy('collateral_list')

    def form_valid(self, form):
        # set created_by to current user
        form.instance.created_by = self.request.user
        return super().form_valid(form)


# ----------------------------------------------------------------
# Update Collateral (admin only)
# ----------------------------------------------------------------
@method_decorator(admin_required, name='dispatch')
class CollateralUpdateView(UpdateView):
    model = Collateral
    form_class = CollateralForm
    template_name = 'collateral_management/collateral_update.html'
    success_url = reverse_lazy('collateral_list')


# ----------------------------------------------------------------
# Delete Collateral (admin only)
# ----------------------------------------------------------------
@method_decorator(admin_required, name='dispatch')
class CollateralDeleteView(DeleteView):
    model = Collateral
    template_name = 'collateral_management/collateral_delete.html'
    success_url = reverse_lazy('collateral_list')


# ----------------------------------------------------------------
# Link Collateral to Campaign
# (Using the bridging table: CampaignCollateral)
# ----------------------------------------------------------------
@admin_required
def link_collateral_to_campaign(request):
    """
    A form to pick which Campaign, which Collateral,
    and optional start_date/end_date for scheduling.
    """
    if request.method == 'POST':
        form = CampaignCollateralForm(request.POST)
        if form.is_valid():
            # Save the bridging record
            obj = form.save(commit=False)
            # You might check if it already exists:
            exists = CampaignCollateral.objects.filter(
                campaign=obj.campaign,
                collateral=obj.collateral
            ).exists()
            if exists:
                messages.warning(request, "That collateral is already linked to this campaign.")
            else:
                obj.save()
                messages.success(request, "Collateral linked to campaign successfully.")
            return redirect('link_collateral_to_campaign')
    else:
        form = CampaignCollateralForm()

    # show existing relationships
    linked = CampaignCollateral.objects.select_related('campaign', 'collateral').all()

    return render(request, 'collateral_management/link_collateral_to_campaign.html', {
        'form': form,
        'linked': linked,
    })


def unlink_collateral_from_campaign(request, pk):
    """
    pk here is the bridging table PK, not the campaign or collateral PK.
    Admin can remove that relationship.
    """
    record = get_object_or_404(CampaignCollateral, pk=pk)
    record.delete()
    messages.success(request, "Collateral unlinked from campaign.")
    return redirect('link_collateral_to_campaign')