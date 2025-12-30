from django.core.management.base import BaseCommand
from sharing_management.models import SecurityQuestion


class Command(BaseCommand):
    help = 'Create default security questions for field representative registration'

    def handle(self, *args, **options):
        # Define default security questions
        default_questions = [
            "What was your childhood nickname?",
            "What is the name of your first pet?",
            "What is your mother's maiden name?",
            "What elementary school did you attend?",
            "What is the name of your favorite teacher?",
            "What was your first car?",
            "What is your favorite movie?",
            "What city were you born in?",
            "What is your favorite food?",
            "What is your best friend's name?",
        ]

        created_count = 0
        skipped_count = 0

        for question_text in default_questions:
            # Use get_or_create to avoid duplicates
            question, created = SecurityQuestion.objects.get_or_create(
                question_txt=question_text,
                defaults={}
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created security question: {question_text}')
                )
            else:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(f'Security question already exists: {question_text}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary: Created {created_count} new security questions, '
                f'skipped {skipped_count} existing questions.'
            )
        )

        # Display all current security questions
        self.stdout.write('\nCurrent security questions in database:')
        for question in SecurityQuestion.objects.all().order_by('id'):
            self.stdout.write(f'  {question.id}: {question.question_txt}')
