# admin_dashboard/urls.py

from django.urls import path, reverse
from django.shortcuts import redirect
from . import views

app_name = "admin_dashboard"


def redirect_to_fieldreps(request):
    """
    Keep campaign context via session if present.
    """
    brand_campaign_id = request.session.get("brand_campaign_id")
    if brand_campaign_id:
        return redirect(f'{reverse("admin_dashboard:fieldrep_list")}?brand_campaign_id={brand_campaign_id}')
    return redirect("admin_dashboard:fieldrep_list")


urlpatterns = [
    # redirect root to field reps list (filtered if session has campaign)
    path("", redirect_to_fieldreps, name="dashboard"),

    # bulk upload
    path("bulk-fieldreps/", views.bulk_upload_fieldreps, name="bulk_upload"),

    # field-rep CRUD
    path("fieldreps/", views.FieldRepListView.as_view(), name="fieldrep_list"),
    path("fieldreps/add/", views.FieldRepCreateView.as_view(), name="fieldrep_add"),
    path("fieldreps/<int:pk>/edit/", views.FieldRepUpdateView.as_view(), name="fieldrep_edit"),
    path("fieldreps/<int:pk>/delete/", views.FieldRepDeleteView.as_view(), name="fieldrep_delete"),

    # doctors CRUD (rep -> doctors)
    path("fieldreps/<int:pk>/doctors/", views.FieldRepDoctorView.as_view(), name="fieldrep_doctors"),

    # legacy/alt route kept (was present in your file) — supported by updated dispatch()
    path("fieldreps/<int:rep_id>/doctors/", views.FieldRepDoctorView.as_view(), name="doctor_list"),

    path("fieldreps/<int:pk_rep>/doctors/<int:pk>/edit/", views.DoctorUpdateView.as_view(), name="doctor_edit"),
    path("fieldreps/<int:pk_rep>/doctors/<int:pk>/delete/", views.DoctorDeleteView.as_view(), name="doctor_delete"),
]
