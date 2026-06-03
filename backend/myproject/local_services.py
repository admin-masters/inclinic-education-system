from __future__ import annotations

from dataclasses import dataclass


LOCAL_SERVICE_HOST = "127.0.0.1"


@dataclass(frozen=True)
class LocalSystemService:
    slug: str
    display_name: str
    host: str
    port: int
    settings_module: str | None = None
    runnable_from_this_repo: bool = False

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


LOCAL_SYSTEM_SERVICES = {
    "inclinic": LocalSystemService(
        slug="inclinic",
        display_name="InClinic",
        host=LOCAL_SERVICE_HOST,
        port=3005,
        settings_module="myproject.settings_v2_local",
        runnable_from_this_repo=True,
    ),
    "rfa": LocalSystemService(
        slug="rfa",
        display_name="RFA",
        host=LOCAL_SERVICE_HOST,
        port=3006,
    ),
    "pe": LocalSystemService(
        slug="pe",
        display_name="PE",
        host=LOCAL_SERVICE_HOST,
        port=3007,
    ),
}


def get_local_service(slug: str) -> LocalSystemService:
    return LOCAL_SYSTEM_SERVICES[slug.lower()]
