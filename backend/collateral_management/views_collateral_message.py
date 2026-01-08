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
    """AJAX endpoint to get collaterals for a selected campaign"""
    campaign_id = request.GET.get('campaign_id')
    
    if not campaign_id:
        return JsonResponse({'error': 'Campaign ID is required'}, status=400)
    
    try:
        campaign = Campaign.objects.get(id=campaign_id, is_active=True)
        collaterals = Collateral.objects.filter(
            campaign=campaign, 
            is_active=True
        ).order_by('title')
        
        collateral_data = [
            {
                'id': collat.id,
                'title': collat.title,
                'type': collat.type
            }
            for collat in collaterals
        ]
        
        return JsonResponse({'collaterals': collateral_data})
    
    except Campaign.DoesNotExist:
        return JsonResponse({'error': 'Campaign not found'}, status=404)
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
