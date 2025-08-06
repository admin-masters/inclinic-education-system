import hashlib
import os
from datetime import datetime
from django.db import connection
from django.contrib.auth.hashers import make_password

# Salt for PBKDF2 hashing - should be stored securely in production
SALT = b'inclinic_salt_2024'

def register_field_representative(field_id, email, whatsapp_number, password, security_question_id, security_answer):
    """
    Register a new field representative with the specified placeholder style.
    
    Args:
        field_id: The field representative ID
        email: Email address
        whatsapp_number: WhatsApp number
        password: Plain text password (will be Django-hashed)
        security_question_id: Foreign key to security_question
        security_answer: Plain text answer (will be PBKDF2-hashed)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Hash the password using Django's make_password
        hashed_password = make_password(password)
        
        # Hash the security answer using PBKDF2
        security_answer_hash = hashlib.pbkdf2_hmac(
            'sha256', 
            security_answer.encode(), 
            SALT, 
            260000
        ).hex()
        
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO sharing_management_fieldrepresentative 
                (field_id, email, whatsapp_number, password, security_question_id, security_answer_hash, auth_method, is_active, created_at, updated_at) 
                VALUES (%s, %s, %s, %s, %s, %s, 'email', 1, NOW(), NOW())
            """, [
                field_id,
                email,
                whatsapp_number,
                hashed_password,
                security_question_id,
                security_answer_hash
            ])
        
        return True
    except Exception as e:
        print(f"Error registering field representative: {e}")
        return False

def validate_forgot_password(email, security_question_id, security_answer):
    """
    Validate forgot password request with the specified placeholder style.
    
    Args:
        email: Email address
        security_question_id: Foreign key to security_question
        security_answer: Plain text answer (will be PBKDF2-hashed for comparison)
    
    Returns:
        bool: True if validation successful, False otherwise
    """
    try:
        # Hash the security answer using PBKDF2
        security_answer_hash = hashlib.pbkdf2_hmac(
            'sha256', 
            security_answer.encode(), 
            SALT, 
            260000
        ).hex()
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM sharing_management_fieldrepresentative 
                WHERE email = %s AND security_question_id = %s AND security_answer_hash = %s
            """, [email, security_question_id, security_answer_hash])
            
            result = cursor.fetchone()
            return result is not None
            
    except Exception as e:
        print(f"Error validating forgot password: {e}")
        return False

def get_security_question_by_email(email):
    """
    Get the security question for a given email.
    
    Args:
        email: Email address
    
    Returns:
        tuple: (security_question_id, question_text) or (None, None) if not found
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT sq.id, sq.question 
                FROM sharing_management_fieldrepresentative fr
                JOIN security_question sq ON fr.security_question_id = sq.id
                WHERE fr.email = %s
                LIMIT 1
            """, [email])
            
            result = cursor.fetchone()
            return result if result else (None, None)
            
    except Exception as e:
        print(f"Error getting security question: {e}")
        return (None, None)

def register_user_management_user(email, username, password, security_answers):
    """
    Register a new user in user_management_user table with security answers.
    
    Args:
        email: Email address
        username: Username (typically same as email)
        password: Plain text password (will be Django-hashed)
        security_answers: List of (question_id, answer) tuples
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with connection.cursor() as cursor:
            # Insert the user with all required fields
            cursor.execute("""
                INSERT INTO user_management_user 
                (email, username, password, temp_password_hash, 
                 is_superuser, first_name, last_name, is_staff, is_active, 
                 date_joined, role, active) 
                VALUES (%s, %s, %s, NULL, 
                        0, %s, %s, 0, 1, 
                        NOW(), 'field_rep', 1)
            """, [
                email, 
                username, 
                make_password(password),
                username.split('@')[0],  # Use part before @ as first_name
                username.split('@')[0]   # Use part before @ as last_name
            ])
            
            user_id = cursor.lastrowid
            
            # Insert security answers
            for question_id, answer in security_answers:
                security_answer_hash = hashlib.pbkdf2_hmac(
                    'sha256', 
                    answer.encode(), 
                    SALT, 
                    260000
                )
                
                cursor.execute("""
                    INSERT INTO user_security_answer 
                    (user_id, question_id, security_answer_hash) 
                    VALUES (%s, %s, %s)
                """, [user_id, question_id, security_answer_hash])
        
        return True
    except Exception as e:
        print(f"Error registering user management user: {e}")
        return False

def set_temp_password(email, system_password):
    """
    Set a temporary system-generated password for a user.
    
    Args:
        email: Email address
        system_password: Plain text system-generated password (will be Django-hashed)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE user_management_user 
                SET temp_password_hash = %s 
                WHERE email = %s
            """, [make_password(system_password), email])
            
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error setting temp password: {e}")
        return False

def copy_prefilled_doctor(rep_id, prefilled_doctor_id):
    """
    Copy a prefilled doctor to doctor_viewer_doctor for a rep.
    
    Args:
        rep_id: The representative/user ID
        prefilled_doctor_id: The ID of the prefilled doctor to copy
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO doctor_viewer_doctor (rep_id, name, email, phone, source) 
                SELECT %s, full_name, email, phone, 'prefill' 
                FROM prefilled_doctor 
                WHERE id = %s
            """, [rep_id, prefilled_doctor_id])
            
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error copying prefilled doctor: {e}")
        return False

def validate_user_forgot_password(email, security_answer):
    """
    Validate forgot password for user_management_user with the specified placeholder style.
    
    Args:
        email: Email address
        security_answer: Plain text answer (will be PBKDF2-hashed for comparison)
    
    Returns:
        bool: True if validation successful, False otherwise
    """
    try:
        # Hash the security answer using PBKDF2
        security_answer_hash = hashlib.pbkdf2_hmac(
            'sha256', 
            security_answer.encode(), 
            SALT, 
            260000
        )
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 1 
                FROM user_security_answer usa 
                JOIN security_question q ON q.id = usa.question_id 
                WHERE usa.user_id = (SELECT id FROM user_management_user WHERE email = %s) 
                AND usa.security_answer_hash = %s 
                LIMIT 1
            """, [email, security_answer_hash])
            
            result = cursor.fetchone()
            return result is not None
            
    except Exception as e:
        print(f"Error validating user forgot password: {e}")
        return False

def get_user_security_questions_by_email(email):
    """
    Get all security questions for a given email in user_management_user.
    
    Args:
        email: Email address
    
    Returns:
        list: List of (question_id, question_text) tuples or empty list if not found
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT sq.id, sq.question 
                FROM user_security_answer usa
                JOIN security_question sq ON usa.question_id = sq.id
                JOIN user_management_user umu ON usa.user_id = umu.id
                WHERE umu.email = %s
            """, [email])
            
            results = cursor.fetchall()
            return results if results else []
            
    except Exception as e:
        print(f"Error getting user security questions: {e}")
        return []

def generate_and_store_otp(field_id, phone_number):
    """
    Generate OTP for WhatsApp login and store it in rep_login_otp table.
    
    Args:
        field_id: The field representative ID
        phone_number: The phone number for WhatsApp
    
    Returns:
        tuple: (success: bool, otp: str, user_id: int, user_data: dict) or (False, None, None, None)
    """
    import secrets
    from datetime import datetime, timedelta
    
    try:
        # First lookup user
        success, user_id, user_data = lookup_user_by_field_and_phone(field_id, phone_number)
        if not success:
            return False, None, None, None
        
        with connection.cursor() as cursor:
            # Generate 6-digit OTP
            otp = str(secrets.randbelow(1000000)).zfill(6)
            
            # Hash the OTP using PBKDF2
            otp_hash = hashlib.pbkdf2_hmac(
                'sha256', 
                otp.encode(), 
                SALT, 
                260000
            )
            
            # Set expiration (10 minutes from now)
            expires_at = datetime.now() + timedelta(minutes=10)
            
            # Store or update OTP record
            cursor.execute("""
                INSERT INTO rep_login_otp (user_id, otp_hash, expires_at, retry_count, sent_at) 
                VALUES (%s, %s, %s, 0, NOW())
                ON DUPLICATE KEY UPDATE 
                otp_hash = VALUES(otp_hash), 
                expires_at = VALUES(expires_at), 
                retry_count = 0
            """, [user_id, otp_hash, expires_at])
            
            return True, otp, user_id, user_data
            
    except Exception as e:
        print(f"Error generating OTP: {e}")
        return False, None, None, None

def log_whatsapp_login_attempt(user_id, success, ip_address=None, user_agent=None):
    """
    Log a WhatsApp login attempt to the audit table.
    
    Args:
        user_id: The user ID
        success: Whether the login was successful
        ip_address: IP address of the login attempt
        user_agent: User agent string
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO login_audit_whatsapp 
                (user_id, success, ip_address, user_agent, created_at) 
                VALUES (%s, %s, %s, %s, NOW())
            """, [user_id, success, ip_address, user_agent])
            
            return True
    except Exception as e:
        print(f"Error logging WhatsApp login attempt: {e}")
        return False


def verify_otp(field_id, phone_number, otp, ip_address=None, user_agent=None):
    """
    Verify OTP for WhatsApp login.
    
    Args:
        field_id: The field representative ID
        phone_number: The phone number for WhatsApp
        otp: The 6-digit OTP entered by user
        ip_address: IP address for audit logging
        user_agent: User agent for audit logging
    
    Returns:
        tuple: (success: bool, user_id: int, user_data: dict) or (False, None, None)
    """
    try:
        # First lookup user
        success, user_id, user_data = lookup_user_by_field_and_phone(field_id, phone_number)
        if not success:
            return False, None, None
        
        with connection.cursor() as cursor:
            # Hash the provided OTP
            otp_hash = hashlib.pbkdf2_hmac(
                'sha256', 
                otp.encode(), 
                SALT, 
                260000
            )
            
            # Check if OTP is valid and not expired
            cursor.execute("""
                SELECT 1 FROM rep_login_otp 
                WHERE user_id = %s AND otp_hash = %s AND expires_at > NOW()
            """, [user_id, otp_hash])
            
            if cursor.fetchone():
                # OTP is valid - delete it and log success
                cursor.execute("DELETE FROM rep_login_otp WHERE user_id = %s", [user_id])
                log_whatsapp_login_attempt(user_id, True, ip_address, user_agent)
                return True, user_id, user_data
            else:
                # OTP is invalid or expired - increment retry count and log failure
                cursor.execute("""
                    UPDATE rep_login_otp 
                    SET retry_count = retry_count + 1 
                    WHERE user_id = %s
                """, [user_id])
                log_whatsapp_login_attempt(user_id, False, ip_address, user_agent)
                return False, None, None
            
    except Exception as e:
        print(f"Error verifying OTP: {e}")
        return False, None, None 

def lookup_user_by_field_and_phone(field_id, phone_e164):
    """
    Lookup user by field_id and phone_number for WhatsApp login.
    
    Args:
        field_id: The field representative ID
        phone_e164: Phone number in E.164 format
    
    Returns:
        tuple: (success: bool, user_id: int, user_data: dict) or (False, None, None)
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, username, email, field_id, phone_number, role, is_active
                FROM user_management_user
                WHERE field_id = %s AND phone_number = %s
                LIMIT 1
            """, [field_id, phone_e164])
            
            result = cursor.fetchone()
            if result:
                user_id, username, email, field_id, phone_number, role, is_active = result
                user_data = {
                    'id': user_id,
                    'username': username,
                    'email': email,
                    'field_id': field_id,
                    'phone_number': phone_number,
                    'role': role,
                    'is_active': is_active
                }
                return True, user_id, user_data
            else:
                return False, None, None
                
    except Exception as e:
        print(f"Error looking up user: {e}")
        return False, None, None


def generate_doctor_verification_otp(phone_e164, short_link_id):
    """
    Generate OTP for doctor verification via WhatsApp.
    
    Args:
        phone_e164: Phone number in E.164 format
        short_link_id: The short link ID for the collateral
    
    Returns:
        tuple: (success: bool, otp: str, otp_id: int) or (False, None, None)
    """
    import secrets
    from datetime import datetime, timedelta
    
    try:
        with connection.cursor() as cursor:
            # Generate 6-digit OTP
            otp = str(secrets.randbelow(1000000)).zfill(6)
            
            # Hash the OTP using PBKDF2
            otp_hash = hashlib.pbkdf2_hmac(
                'sha256', 
                otp.encode(), 
                SALT, 
                260000
            )
            
            # Set expiration (10 minutes from now)
            expires_at = datetime.now() + timedelta(minutes=10)
            
            # Store OTP record
            cursor.execute("""
                INSERT INTO doctor_verification_otp 
                (phone_e164, otp_hash, short_link_id, expires_at, created_at) 
                VALUES (%s, %s, %s, %s, NOW())
            """, [phone_e164, otp_hash, short_link_id, expires_at])
            
            otp_id = cursor.lastrowid
            
            # TODO: Integrate with actual WhatsApp API (Twilio, MessageBird, etc.)
            # For now, we'll simulate the WhatsApp message
            try:
                # This is a placeholder for actual WhatsApp API integration
                # In production, replace this with your WhatsApp API provider
                print(f"📱 WhatsApp OTP sent to {phone_e164}: {otp}")
                
                # Example WhatsApp API integration (uncomment and configure):
                # import requests
                # 
                # # Option 1: Twilio WhatsApp API
                # # from twilio.rest import Client
                # # client = Client('your_account_sid', 'your_auth_token')
                # # message = client.messages.create(
                # #     from_='whatsapp:+14155238886',  # Your Twilio WhatsApp number
                # #     body=f'Your verification OTP is: {otp}. Valid for 10 minutes.',
                # #     to=f'whatsapp:{phone_e164}'
                # # )
                # 
                # # Option 2: MessageBird WhatsApp API
                # # import messagebird
                # # client = messagebird.Client('your_access_key')
                # # message = client.message_create(
                # #     originator='YourBusiness',
                # #     recipients=[phone_e164],
                # #     body=f'Your verification OTP is: {otp}. Valid for 10 minutes.'
                # # )
                # 
                # # Option 3: Generic HTTP API (replace with your provider)
                # # whatsapp_api_url = "https://your-whatsapp-api.com/send"
                # # payload = {
                # #     "to": phone_e164,
                # #     "message": f"Your verification OTP is: {otp}. Valid for 10 minutes.",
                # #     "api_key": "your_api_key"
                # # }
                # # response = requests.post(whatsapp_api_url, json=payload)
                # # if response.status_code != 200:
                # #     print(f"WhatsApp API error: {response.text}")
                # #     return False, None, None
                
                # For development/testing - remove this in production
                print(f"🔧 Development Mode: OTP {otp} would be sent to {phone_e164} via WhatsApp")
                
            except Exception as whatsapp_error:
                print(f"WhatsApp API error: {whatsapp_error}")
                # Don't fail the entire operation if WhatsApp fails
                # In production, you might want to handle this differently
            
            return True, otp, otp_id
            
    except Exception as e:
        print(f"Error generating doctor verification OTP: {e}")
        return False, None, None


def verify_doctor_otp(phone_e164, short_link_id, otp):
    """
    Verify OTP for doctor verification using the two-step approach.
    
    Args:
        phone_e164: Phone number in E.164 format
        short_link_id: The short link ID for the collateral
        otp: The 6-digit OTP entered by doctor
    
    Returns:
        tuple: (success: bool, otp_id: int) or (False, None)
    """
    try:
        with connection.cursor() as cursor:
            # Step 1: Get the latest OTP record for this phone and short_link
            cursor.execute("""
                SELECT id, otp_hash, expires_at
                FROM doctor_verification_otp
                WHERE phone_e164 = %s
                  AND short_link_id = %s
                  AND verified_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
            """, [phone_e164, short_link_id])
            
            result = cursor.fetchone()
            if not result:
                return False, None
                
            otp_id, stored_otp_hash, expires_at = result
            
            # Check if OTP is expired
            if expires_at < datetime.now():
                return False, None
                
            # Step 2: Hash the provided OTP and compare
            provided_otp_hash = hashlib.pbkdf2_hmac(
                'sha256', 
                otp.encode(), 
                SALT, 
                260000
            )
            
            # Compare hashes
            if provided_otp_hash == stored_otp_hash:
                # Step 3: Mark as verified
                cursor.execute("""
                    UPDATE doctor_verification_otp
                    SET verified_at = NOW()
                    WHERE id = %s
                """, [otp_id])
                return True, otp_id
            else:
                return False, None
                
    except Exception as e:
        print(f"Error verifying doctor OTP: {e}")
        return False, None


def log_manual_doctor_share(short_link_id, field_rep_id, phone_e164, collateral_id):
    """
    Log a manual doctor share via WhatsApp.
    
    Args:
        short_link_id: The short link ID for the collateral
        field_rep_id: The field representative ID (can be User ID or field_rep_id)
        phone_e164: Phone number in E.164 format
        collateral_id: The collateral ID
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # First, try to get the User object for this field_rep_id
        from user_management.models import User
        
        # Try to find user by username pattern
        user = None
        try:
            user = User.objects.get(username=f"field_rep_{field_rep_id}")
        except User.DoesNotExist:
            # If not found, try to find by ID
            try:
                user = User.objects.get(id=field_rep_id)
            except User.DoesNotExist:
                # If still not found, create a new user
                user, created = User.objects.get_or_create(
                    username=f"field_rep_{field_rep_id}",
                    defaults={
                        'email': f"field_rep_{field_rep_id}@example.com",
                        'first_name': f"Field Rep {field_rep_id}"
                    }
                )
        
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO sharing_management_sharelog
                (short_link_id, field_rep_id, doctor_identifier, share_channel, share_timestamp, created_at, updated_at, collateral_id)
                VALUES (%s, %s, %s, 'WhatsApp', NOW(), NOW(), NOW(), %s)
            """, [short_link_id, user.id, phone_e164, collateral_id])
            
            return True
    except Exception as e:
        print(f"Error logging manual doctor share: {e}")
        return False


def share_prefilled_doctor(rep_id, prefilled_doctor_id, short_link_id, collateral_id):
    """
    Share a prefilled doctor via WhatsApp.
    
    Args:
        rep_id: The field representative ID
        prefilled_doctor_id: The ID of the prefilled doctor to share
        short_link_id: The short link ID for the collateral
        collateral_id: The collateral ID
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with connection.cursor() as cursor:
            # Step 1: Copy doctor to personal list (if absent)
            cursor.execute("""
                INSERT INTO doctor_viewer_doctor (rep_id, name, phone, source)
                SELECT %s, full_name, phone, 'prefill_wa'
                FROM prefilled_doctor
                WHERE id = %s
                ON DUPLICATE KEY UPDATE doctor_viewer_doctor.id = doctor_viewer_doctor.id
            """, [rep_id, prefilled_doctor_id])
            
            # Step 2: Get the doctor's phone number for logging
            cursor.execute("""
                SELECT phone FROM prefilled_doctor WHERE id = %s
            """, [prefilled_doctor_id])
            
            result = cursor.fetchone()
            if not result:
                print(f"Prefilled doctor with ID {prefilled_doctor_id} not found")
                return False
            
            phone_e164 = result[0]
            
            # Step 3: Insert share log (channel = 'WhatsApp')
            cursor.execute("""
                INSERT INTO sharing_management_sharelog
                (short_link_id, field_rep_id, doctor_identifier, share_channel, share_timestamp, created_at, updated_at, collateral_id)
                VALUES (%s, %s, %s, 'WhatsApp', NOW(), NOW(), NOW(), %s)
            """, [short_link_id, rep_id, phone_e164, collateral_id])
            
            return True
    except Exception as e:
        print(f"Error sharing prefilled doctor: {e}")
        return False


def verify_doctor_whatsapp_number(phone_e164, short_link_id):
    """
    Verify if the provided WhatsApp number matches the one used to share the collateral.
    
    Args:
        phone_e164: Phone number in E.164 format
        short_link_id: The short link ID for the collateral
    
    Returns:
        bool: True if WhatsApp number matches, False otherwise
    """
    try:
        with connection.cursor() as cursor:
            # Check if this phone number was used to share this collateral
            cursor.execute("""
                SELECT 1 FROM sharing_management_sharelog
                WHERE short_link_id = %s 
                  AND doctor_identifier = %s
                  AND share_channel = 'WhatsApp'
                LIMIT 1
            """, [short_link_id, phone_e164])
            
            result = cursor.fetchone()
            return result is not None
            
    except Exception as e:
        print(f"Error verifying doctor WhatsApp number: {e}")
        return False


def grant_download_access(short_link_id):
    """
    Grant download access by marking doctor engagement.
    
    Args:
        short_link_id: The short link ID for the collateral
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO doctor_viewer_doctorengagement
                (short_link_id, view_timestamp, pdf_completed, last_page_scrolled,
                 video_watch_percentage, created_at, updated_at, status)
                VALUES (%s, NOW(), 0, 0, 0, NOW(), NOW(), 1)
                ON DUPLICATE KEY UPDATE
                view_timestamp = NOW(),
                status = 1,
                updated_at = NOW()
            """, [short_link_id])
            
            return True
    except Exception as e:
        print(f"Error granting download access: {e}")
        return False

def authenticate_field_representative(email, password):
    """
    Authenticate a field representative using email and password.
    
    Args:
        email: Email address
        password: Plain text password
    
    Returns:
        tuple: (user_id, field_id, email) if successful, (None, None, None) if failed
    """
    try:
        from django.contrib.auth.hashers import check_password
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, field_id, email, password 
                FROM sharing_management_fieldrepresentative 
                WHERE email = %s AND is_active = 1
            """, [email])
            
            result = cursor.fetchone()
            if result:
                user_id, field_id, email, hashed_password = result
                if check_password(password, hashed_password):
                    return user_id, field_id, email
            return None, None, None
            
    except Exception as e:
        print(f"Error authenticating field representative: {e}")
        return None, None, None

def reset_field_representative_password(email, new_password):
    """
    Reset password for a field representative.
    
    Args:
        email: Email address
        new_password: New plain text password
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Hash the new password using Django's make_password
        hashed_password = make_password(new_password)
        
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE sharing_management_fieldrepresentative 
                SET password = %s, updated_at = NOW()
                WHERE email = %s AND is_active = 1
            """, [hashed_password, email])
            
            return cursor.rowcount > 0
            
    except Exception as e:
        print(f"Error resetting password: {e}")
        return False 