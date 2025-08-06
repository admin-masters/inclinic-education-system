from django.apps import apps

def load_secrets(env='production'):
    """Load secrets once from DB and return as a dictionary."""
    Secret = apps.get_model('user_management', 'Secret')  # Lazy loading the model
    secrets = Secret.objects.filter(environment=env)
    return {s.key_name: s.key_value for s in secrets}
