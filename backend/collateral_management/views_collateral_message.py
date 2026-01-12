from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from .models import CollateralMessage, Collateral
from campaign_management.models import Campaign
from .forms import CollateralMessageForm, CollateralMessageSearchForm


@login_required
def collateral_message_list(request):
    """List all collateral messages with search functionality"""
    form = CollateralMessageSearchForm(request.GET)
    messages_list = CollateralMessage.objects.select_related('campaign', 'collateral')
    
    # Apply filters
    if form.is_valid():
        if form.cleaned_data.get('brand_campaign_id'):
            messages_list = messages_list.filter(
                campaign__brand_campaign_id__icontains=form.cleaned_data['brand_campaign_id']
            )
        if form.cleaned_data.get('collateral_id'):
            messages_list = messages_list.filter(
                collateral_id=form.cleaned_data['collateral_id']
            )
    
    context = {
        'form': form,
        'messages': messages_list.order_by('-created_at'),
        'title': 'Collateral Messages Management'
    }
    return render(request, 'collateral_management/collateral_message_list.html', context)


@login_required
def collateral_message_create(request):
    """Create a new collateral message"""
    if request.method == 'POST':
        form = CollateralMessageForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Collateral message created successfully!')
            return redirect('collateral_message_list')
    else:
        form = CollateralMessageForm()
    
    context = {
        'form': form,
        'title': 'Add Collateral Message',
        'action': 'Create'
    }
    return render(request, 'collateral_management/collateral_message_form.html', context)


@login_required
def collateral_message_edit(request, pk):
    """Edit an existing collateral message"""
    message = get_object_or_404(CollateralMessage, pk=pk)
    
    if request.method == 'POST':
        form = CollateralMessageForm(request.POST, instance=message)
        if form.is_valid():
            form.save()
            messages.success(request, 'Collateral message updated successfully!')
            return redirect('collateral_message_list')
    else:
        form = CollateralMessageForm(instance=message)
    
    context = {
        'form': form,
        'message': message,
        'title': 'Edit Collateral Message',
        'action': 'Update'
    }
    return render(request, 'collateral_management/collateral_message_form.html', context)


@login_required
def collateral_message_delete(request, pk):
    """Delete a collateral message"""
    message = get_object_or_404(CollateralMessage, pk=pk)
    
    if request.method == 'POST':
        message.delete()
        messages.success(request, 'Collateral message deleted successfully!')
        return redirect('collateral_message_list')
    
    context = {
        'message': message,
        'title': 'Delete Collateral Message'
    }
    return render(request, 'collateral_management/collateral_message_confirm_delete.html', context)


@login_required
@require_http_methods(["GET"])
def get_collaterals_by_campaign(request):
    """Get collaterals for a specific campaign (AJAX endpoint).

    This endpoint is used by the Collateral Message create/edit form to populate
    the "Collateral" dropdown after a campaign is selected.

    Rules:
      - Return ONLY Collateral rows where is_active=True.
      - Prefer the bridging table collateral_management.CampaignCollateral (campaign ↔ collateral).
      - If the deployment still uses a direct FK (Collateral.campaign), support that as a fallback.
      - If start_date / end_date exist on CampaignCollateral, apply an "active window" filter
        using DATE comparisons (to avoid midnight cutoff issues).
    """
    campaign_id_str = (request.GET.get('campaign_id') or '').strip()

    if not campaign_id_str.isdigit():
        return JsonResponse({'collaterals': []})

    campaign_id = int(campaign_id_str)

    try:
        # Campaign model uses 'status' in this codebase (not 'is_active').
        campaign = Campaign.objects.get(pk=campaign_id)
    except Campaign.DoesNotExist:
        return JsonResponse({'collaterals': []})

    try:
        from django.db.models import Q
        from django.utils import timezone
        today = timezone.localdate()

        # Start with an empty queryset and UNION the available sources.
        collaterals_qs = Collateral.objects.none()

        # 1) Preferred: collateral_management.CampaignCollateral bridge
        try:
            from .models import CampaignCollateral as CMCampaignCollateral  # type: ignore

            window_q = (
                (Q(start_date__isnull=True) | Q(start_date__date__lte=today)) &
                (Q(end_date__isnull=True) | Q(end_date__date__gte=today))
            )

            cc_ids = (
                CMCampaignCollateral.objects
                .filter(campaign=campaign)
                .filter(window_q)
                .values_list('collateral_id', flat=True)
            )

            collaterals_qs = collaterals_qs | Collateral.objects.filter(id__in=cc_ids, is_active=True)
        except Exception:
            # If the bridge model/table is unavailable, ignore and try fallback below.
            pass

        # 2) Fallback: direct FK Collateral.campaign (some older deployments)
        try:
            # Only attempt if the field exists; avoids FieldError in newer schemas.
            Collateral._meta.get_field('campaign')
            collaterals_qs = collaterals_qs | Collateral.objects.filter(campaign=campaign, is_active=True)
        except Exception:
            pass

        collaterals_qs = collaterals_qs.distinct().order_by('title')

        collaterals_data = [
            {
                'id': c.id,
                'title': getattr(c, 'title', str(c)),
                'type': getattr(c, 'type', ''),
            }
            for c in collaterals_qs
        ]

        return JsonResponse({'collaterals': collaterals_data})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_collateral_message(request):
    """Get custom message for a specific collateral in a campaign"""
    campaign_id = request.GET.get('campaign_id')
    collateral_id = request.GET.get('collateral_id')
    
    if not campaign_id or not collateral_id:
        return JsonResponse({'error': 'Campaign ID and Collateral ID are required'}, status=400)
    
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        collateral = Collateral.objects.get(id=collateral_id)
        
        message = CollateralMessage.objects.filter(
            campaign=campaign,
            collateral=collateral,
            is_active=True
        ).first()
        
        if message:
            return JsonResponse({
                'success': True,
                'message': message.message,
                'campaign_id': campaign.brand_campaign_id,
                'collateral_title': collateral.title
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'No custom message found for this collateral'
            })
    
    except (Campaign.DoesNotExist, Collateral.DoesNotExist):
        return JsonResponse({'error': 'Campaign or Collateral not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
