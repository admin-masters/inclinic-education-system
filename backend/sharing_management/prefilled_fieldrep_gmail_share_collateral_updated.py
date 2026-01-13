def prefilled_fieldrep_gmail_share_collateral_updated(request):
    import urllib.parse
    from django.utils import timezone
    from django.db.models import Q
    from django.conf import settings
    from django.http import JsonResponse
    from datetime import timedelta
    from sharing_management.views import find_or_create_short_link, get_brand_specific_message
    
    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    brand_campaign_id = request.GET.get('campaign') or request.session.get('brand_campaign_id')
    
    # Store brand_campaign_id in session if provided in URL
    if 'campaign' in request.GET:
        request.session['brand_campaign_id'] = brand_campaign_id
    
    if not field_rep_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Please login first.'}, status=401)
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_login')
    
    # Get doctors assigned to THIS field rep (from admin dashboard)
    try:
        from doctor_viewer.models import Doctor, DoctorEngagement
        from user_management.models import User
        from sharing_management.models import ShareLog, ShortLink
        from collateral_management.models import Collateral, CampaignCollateral
        
        # Get the field rep user object by field_id (since field_rep_id is from FieldRepresentative table)
        field_rep_user = None
        if field_rep_field_id:
            try:
                field_rep_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
            except User.DoesNotExist:
                # Try to find by email/gmail as fallback
                if field_rep_email:
                    try:
                        field_rep_user = User.objects.filter(email=field_rep_email, role='field_rep').first()
                    except:
                        pass
        
        doctors_list = []
        if field_rep_user:
            # Get all doctors assigned to this field rep
            assigned_doctors = Doctor.objects.filter(rep=field_rep_user)
            
            # Get the selected collateral ID if provided
            selected_collateral_id = request.GET.get('collateral')
            
            # Prepare the doctors list with status information
            for doc in assigned_doctors:
                # Default status is 'not_shared'
                status = 'not_shared'
                last_shared = None
                
                # Check if this doctor has any share logs for the selected collateral
                if selected_collateral_id:
                    phone_val = doc.phone or ''
                    phone_clean = phone_val.replace('+', '').replace(' ', '').replace('-', '')
                    possible_ids = [phone_val]
                    if phone_clean and len(phone_clean) == 10:
                        possible_ids.append(f"+91{phone_clean}")
                        possible_ids.append(f"91{phone_clean}")
                    elif phone_clean.startswith('91'):
                        possible_ids.append(f"+{phone_clean}")

                    share_log_q = Q(doctor_identifier__in=possible_ids) & Q(collateral_id=selected_collateral_id)

                    rep_filters = Q()
                    rep_ids = []
                    if field_rep_user and getattr(field_rep_user, 'id', None):
                        rep_ids.append(field_rep_user.id)
                    if rep_ids:
                        rep_filters |= Q(field_rep_id__in=rep_ids)
                    rep_filters |= Q(field_rep__role='field_rep')
                    share_log_q &= rep_filters

                    share_log = ShareLog.objects.filter(share_log_q).order_by('-share_timestamp').first()

                    if share_log:
                        last_shared = share_log.share_timestamp
                        status = 'sent'
                        try:
                            from doctor_viewer.models import DoctorEngagement
                            opened = DoctorEngagement.objects.filter(short_link_id=share_log.short_link_id).exists()
                            if opened:
                                status = 'opened'
                            else:
                                six_days_ago = timezone.now() - timedelta(days=6)
                                if share_log.share_timestamp < six_days_ago:
                                    status = 'reminder'
                        except Exception:
                            pass
                
                doctors_list.append({
                    'id': doc.id,
                    'name': doc.name or 'Unnamed Doctor',
                    'phone': doc.phone or '',
                    'email': doc.email or '',
                    'status': status,
                    'last_shared': last_shared,
                    'specialty': doc.specialty or '',
                    'city': doc.city or '',
                })
        
        # If no doctors found, try to get prefilled doctors as fallback
        if not doctors_list:
            try:
                rep_pk, rep_field_id, rep_smg_id = _get_current_rep_ids(request)
                doctors_data = _fetch_assigned_prefilled_doctors(rep_pk, rep_field_id, rep_smg_id)
                doctors_list = [
                    {
                        'id': d[0],
                        'name': d[1],
                        'phone': d[2],
                        'email': d[3],
                        'specialty': d[4],
                        'city': d[5],
                        'status': 'not_shared',
                        'last_shared': None
                    }
                    for d in doctors_data
                ]
            except Exception as e:
                print(f"Error fetching prefilled doctors: {e}")
        
        if not doctors_list:
            messages.info(request, "No doctors are assigned to your account.")
            print("[DEBUG] No doctors found for field rep:", field_rep_user)
        else:
            print(f"[DEBUG] Found {len(doctors_list)} doctors for field rep")
            
    except Exception as e:
        import traceback
        print(f"[ERROR] Error in doctor query: {str(e)}\n{traceback.format_exc()}")
        doctors_list = []
        
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral, CampaignCollateral
        from user_management.models import User
        from campaign_management.models import CampaignCollateral as CMCampaignCollateral
        
        # Initialize empty list for collaterals
        collaterals = []
        
        if brand_campaign_id and brand_campaign_id != 'all':
            print(f"[DEBUG] Filtering collaterals for brand_campaign_id: {brand_campaign_id}")
            
            # First from campaign_management.CampaignCollateral
            collaterals = Collateral.objects.filter(is_active=True)
            messages.info(request, "Showing all available collaterals as no specific campaign is selected.")
        
        # Get or create a user for this field rep (for short link creation)
        try:
            actual_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
        except User.DoesNotExist:
            # Try to get or create user by email
            if field_rep_email:
                actual_user, created = User.objects.get_or_create(
                    username=f"field_rep_{field_rep_id}",
                    defaults={
                        'email': field_rep_email,
                        'first_name': f"Field Rep {field_rep_field_id or field_rep_id}",
                        'role': 'field_rep',
                        'field_id': field_rep_field_id or f"FR{field_rep_id}"
                    }
                )
            else:
                actual_user = request.user if request.user.is_authenticated else None
        
        # Convert to list format for template
        collaterals_list = []
        for collateral in collaterals:
            try:
                # Create short link for each collateral
                short_link = find_or_create_short_link(collateral, actual_user)
                collaterals_list.append({
                    'id': collateral.id,
                    'name': getattr(collateral, 'title', getattr(collateral, 'item_name', 'Untitled')),
                    'description': getattr(collateral, 'description', ''),
                    'link': request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/")
                })
            except Exception as e:
                print(f"Error creating short link for collateral {getattr(collateral, 'id', 'unknown')}: {e}")
                continue
    except Exception as e:
        collaterals_list = []
        messages.error(request, 'Error loading collaterals. Please try again.')
        print(f"Error in collateral loading: {e}")
    
    if request.method == 'POST':
        try:
            doctor_id_str = request.POST.get('doctor_id', '').strip()
            collateral_id_str = request.POST.get('collateral', '').strip()
            
            if not doctor_id_str or not collateral_id_str:
                messages.error(request, 'Please select both doctor and collateral.')
                return redirect('prefilled_fieldrep_gmail_share_collateral')
            
            doctor_id = int(doctor_id_str)
            collateral_id = int(collateral_id_str)
            
            # Find the selected doctor and collateral
            selected_doctor = next((d for d in doctors_list if d['id'] == doctor_id), None)
            selected_collateral = next((c for c in collaterals_list if c['id'] == collateral_id), None)
            
            if not selected_doctor:
                messages.error(request, f'Doctor with ID {doctor_id} not found. Please select a valid doctor.')
                return redirect('prefilled_fieldrep_gmail_share_collateral')
            
            if not selected_collateral:
                messages.error(request, f'Collateral with ID {collateral_id} not found. Please select a valid collateral.')
                return redirect('prefilled_fieldrep_gmail_share_collateral')
            
            # Now we know both exist, proceed with sharing
            try:
                from .models import ShareLog
                from collateral_management.models import Collateral
                from user_management.models import User
                from shortlink_management.models import ShortLink
                from django.utils import timezone
                
                # Get or create a user for this field rep (for short link creation)
                try:
                    actual_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
                except User.DoesNotExist:
                    # Try to get or create user by email
                    if field_rep_email:
                        actual_user, created = User.objects.get_or_create(
                            username=f"field_rep_{field_rep_id}",
                            defaults={
                                'email': field_rep_email,
                                'first_name': f"Field Rep {field_rep_field_id or field_rep_id}",
                                'role': 'field_rep',
                                'field_id': field_rep_field_id or f"FR{field_rep_id}"
                            }
                        )
                    else:
                        actual_user = request.user if request.user.is_authenticated else None
                
                if not actual_user:
                    messages.error(request, 'Unable to create user for short link. Please try again.')
                    return redirect('prefilled_fieldrep_gmail_share_collateral')
                
                # Get or create short link for this collateral
                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, actual_user)
                
                # Create share log entry
                share_log = ShareLog.objects.create(
                    field_rep=actual_user,
                    doctor_identifier=selected_doctor.get('phone', ''),
                    share_channel='WhatsApp',
                    short_link=short_link,
                    collateral=collateral_obj,
                    share_timestamp=timezone.now(),
                )
                
                # Update doctor's status in the current session
                for doc in doctors_list:
                    if doc['id'] == doctor_id:
                        doc['status'] = 'shared'
                        doc['last_shared'] = timezone.now()
                        break
                
                # Get brand-specific message
                message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                
                # Clean phone number for WhatsApp URL (remove +91, +, spaces, etc.)
                clean_phone = selected_doctor['phone'].replace('+91', '').replace('+', '').replace(' ', '').replace('-', '')
                
                # Create WhatsApp share URL
                wa_url = f"https://wa.me/91{clean_phone}?text={urllib.parse.quote(message)}"
                
                # If it's an AJAX request, return JSON response
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'wa_url': wa_url,
                        'doctor_id': doctor_id,
                        'status': 'shared',
                        'last_shared': timezone.now().isoformat(),
                        'message': f'Message prepared for {selected_doctor["name"]}.'
                    })
                
                # For regular form submission, redirect to WhatsApp
                return redirect(wa_url)
                    
            except Exception as e:
                print(f"Error in sharing collateral: {e}")
                import traceback
                traceback.print_exc()
                messages.error(request, f'Error sharing collateral: {str(e)}')
                return redirect('prefilled_fieldrep_gmail_share_collateral')
                messages.error(request, 'Error sharing collateral. Please try again.')
                return redirect('prefilled_fieldrep_gmail_share_collateral')
                
        except ValueError as ve:
            print(f"ValueError in form submission: {ve}")
            messages.error(request, 'Invalid doctor or collateral ID. Please select valid options.')
            return redirect('prefilled_fieldrep_gmail_share_collateral')
        except Exception as e:
            print(f"Unexpected error in form submission: {e}")
            messages.error(request, 'An error occurred. Please try again.')
            return redirect('prefilled_fieldrep_gmail_share_collateral')
    
    # Debug information
    print(f"[DEBUG] Field Rep ID: {field_rep_id}")
    print(f"[DEBUG] Field Rep Email: {field_rep_email}")
    print(f"[DEBUG] Field Rep Field ID: {field_rep_field_id}")
    print(f"[DEBUG] Brand Campaign ID: {brand_campaign_id}")
    print(f"[DEBUG] Number of doctors: {len(doctors_list) if doctors_list else 0}")
    print(f"[DEBUG] Number of collaterals: {len(collaterals_list) if collaterals_list else 0}")
    
    context = {
        'fieldrep_id': field_rep_field_id or field_rep_id,
        'fieldrep_email': field_rep_email,
        'doctors': doctors_list,
        'collaterals': collaterals_list,
        'selected_collateral_id': request.GET.get('collateral'),
        'campaign_id': brand_campaign_id,
    }
    
    print("[DEBUG] Rendering template with context:", {
        'fieldrep_id': field_rep_field_id or 'Unknown',
        'fieldrep_email': field_rep_email,
        'doctors_count': len(doctors_list) if doctors_list else 0,
        'collaterals_count': len(collaterals_list) if collaterals_list else 0
    })
    
    return render(request, 'sharing_management/prefilled_fieldrep_gmail_share_collateral.html', context)
