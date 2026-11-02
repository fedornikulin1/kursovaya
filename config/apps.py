from django.contrib.admin.apps import AdminConfig


class CampusAdminConfig(AdminConfig):
    default_site = "config.admin_site.CampusAdminSite"
