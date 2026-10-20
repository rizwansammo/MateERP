from django.urls import path

from .views import FileContentView

urlpatterns = [
    path("files/<uuid:file_id>/content/", FileContentView.as_view(), name="file-content"),
]
