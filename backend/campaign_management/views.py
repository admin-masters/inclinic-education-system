# campaign_management/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.contrib import messages

from .models import Campaign, CampaignAssignment
from .forms import CampaignForm, CampaignAssignmentForm
from .decorators import admin_required

# ------------------------------------------------------------------------
# Campaign List (open to all roles to see a list, but optional restrict)
# ------------------------------------------------------------------------
class CampaignListView(ListView):
    model = Campaign
    template_name = 'campaign_management/campaign_list.html'
    context_object_name = 'campaigns'
    ordering = ['-created_at']  # most recent first


# ------------------------------------------------------------------------
# View Campaign Details
# ------------------------------------------------------------------------
class CampaignDetailView(DetailView):
    model = Campaign
    template_name = 'campaign_management/campaign_detail.html'
    context_object_name = 'campaign'


# ------------------------------------------------------------------------
# Create Campaign (admin only)
# ------------------------------------------------------------------------
@method_decorator(admin_required, name='dispatch')
class CampaignCreateView(CreateView):
    model = Campaign
    form_class = CampaignForm
    template_name = 'campaign_management/campaign_create.html'
    success_url = reverse_lazy('campaign_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


# ------------------------------------------------------------------------
# Update Campaign (admin only)
# ------------------------------------------------------------------------
@method_decorator(admin_required, name='dispatch')
class CampaignUpdateView(UpdateView):
    model = Campaign
    form_class = CampaignForm
    template_name = 'campaign_management/campaign_update.html'
    success_url = reverse_lazy('campaign_list')


# ------------------------------------------------------------------------
# Delete Campaign (admin only) - optional if you want delete capability
# ------------------------------------------------------------------------
@method_decorator(admin_required, name='dispatch')
class CampaignDeleteView(DeleteView):
    model = Campaign
    template_name = 'campaign_management/campaign_delete.html'
    success_url = reverse_lazy('campaign_list')


# ------------------------------------------------------------------------
# Assign Field Reps to a Campaign
# ------------------------------------------------------------------------
@admin_required
def assign_field_reps(request, pk):
    """
    Show current assignments, allow admin to add new Field Rep or remove existing.
    """
    campaign = get_object_or_404(Campaign, pk=pk)

    if request.method == 'POST':
        form = CampaignAssignmentForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.campaign = campaign
            # Enforce unique constraint
            if not CampaignAssignment.objects.filter(campaign=campaign, field_rep=assignment.field_rep).exists():
                assignment.save()
                messages.success(request, "Field Rep assigned successfully.")
            else:
                messages.warning(request, "That Field Rep is already assigned.")
            return redirect('assign_field_reps', pk=campaign.id)
    else:
        form = CampaignAssignmentForm()
        # override the campaign field if you want to hide it in the form
        form.fields['campaign'].initial = campaign.id
        form.fields['campaign'].widget = forms.HiddenInput()

    # Gather existing assignments
    assignments = CampaignAssignment.objects.filter(campaign=campaign).select_related('field_rep')

    return render(request, 'campaign_management/assign_field_reps.html', {
        'campaign': campaign,
        'form': form,
        'assignments': assignments
    })


def remove_field_rep(request, pk, assignment_id):
    """
    Optional: remove an assignment. Admin only.
    """
    campaign = get_object_or_404(Campaign, pk=pk)
    assignment = get_object_or_404(CampaignAssignment, pk=assignment_id, campaign=campaign)
    assignment.delete()
    messages.success(request, "Field Rep unassigned successfully.")
    return redirect('assign_field_reps', pk=campaign.id)