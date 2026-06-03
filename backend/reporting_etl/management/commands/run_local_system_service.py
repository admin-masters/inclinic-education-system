from __future__ import annotations

import os

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from myproject.local_services import LOCAL_SYSTEM_SERVICES, get_local_service


class Command(BaseCommand):
    help = "Run a configured local system service on its reserved localhost port."

    def add_arguments(self, parser):
        parser.add_argument(
            "service",
            nargs="?",
            default="inclinic",
            choices=sorted(LOCAL_SYSTEM_SERVICES),
            help="Local service to run. Only InClinic is runnable from this repo.",
        )
        parser.add_argument("--host", default="")
        parser.add_argument("--port", type=int, default=0)
        parser.add_argument("--noreload", action="store_true")
        parser.add_argument("--list", action="store_true", help="Show configured services and exit.")

    def handle(self, *args, **options):
        if options["list"]:
            self.print_services()
            return

        service = get_local_service(options["service"])
        if not service.runnable_from_this_repo:
            raise CommandError(
                f"{service.display_name} is reserved for {service.url}, "
                "but it is not runnable from the InClinic repo."
            )

        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        if service.settings_module and settings_module != service.settings_module:
            self.stdout.write(
                self.style.WARNING(
                    f"Recommended settings for {service.display_name}: {service.settings_module}. "
                    f"Current: {settings_module or '(default)'}."
                )
            )

        host = options["host"] or service.host
        port = options["port"] or service.port
        addrport = f"{host}:{port}"

        self.stdout.write(f"Starting {service.display_name} at http://{addrport}/")
        self.print_services(active=service.slug, host=host, port=port)
        call_command(
            "runserver",
            addrport,
            use_reloader=not options["noreload"],
            use_threading=True,
        )

    def print_services(self, *, active: str = "", host: str = "", port: int = 0):
        for name, service in LOCAL_SYSTEM_SERVICES.items():
            marker = "*" if name == active else "-"
            service_host = host if name == active and host else service.host
            service_port = port if name == active and port else service.port
            runnable = "runnable" if service.runnable_from_this_repo else "reserved"
            self.stdout.write(
                f"{marker} {service.display_name}: http://{service_host}:{service_port}/ ({runnable})"
            )
