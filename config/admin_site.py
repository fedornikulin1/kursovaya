from django.contrib.admin import AdminSite
from django.urls import reverse


class WorkspaceAdminMixin:
    """Keep list headings concise while retaining native filters and permissions."""

    def changelist_view(self, request, extra_context=None):
        context = {"title": self.model._meta.verbose_name_plural.capitalize()}
        context.update(extra_context or {})
        return super().changelist_view(request, extra_context=context)


class CampusAdminSite(AdminSite):
    site_header = "ДоскаСВФУ · управление"
    site_title = "Управление ДоскойСВФУ"
    index_title = "Обзор площадки"
    index_template = "admin/campus_index.html"

    def index(self, request, extra_context=None):
        from ads.models import Ad, Review
        from django.contrib.auth import get_user_model
        from support.models import SupportTicket

        cards = []
        for model, label, condition, tone in [
            (SupportTicket, "Ждут ответа", {"status": "open"}, "blue"),
            (Ad, "Активных объявлений", {"status": "active"}, "green"),
            (get_user_model(), "Пользователей", {"is_active": True}, "violet"),
            (Review, "Отзывов", {}, "amber"),
        ]:
            opts = model._meta
            if request.user.has_perm(
                f"{opts.app_label}.view_{opts.model_name}"
            ) or request.user.has_perm(f"{opts.app_label}.change_{opts.model_name}"):
                url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
                if model is SupportTicket:
                    url += "?status__exact=open"
                cards.append(
                    {
                        "label": label,
                        "count": model.objects.filter(**condition).count(),
                        "url": url,
                        "tone": tone,
                    }
                )
        context = {"dashboard_cards": cards}
        if request.user.has_perm("support.view_supportticket") or request.user.has_perm(
            "support.change_supportticket"
        ):
            context["support_queue"] = (
                SupportTicket.objects.filter(status="open")
                .select_related("user")
                .order_by("created_at", "pk")[:5]
            )
        context.update(extra_context or {})
        return super().index(request, context)

    def get_app_list(self, request, app_label=None):
        apps = super().get_app_list(request, app_label)
        names = {
            "Ad": "Объявления",
            "AdImage": "Фотографии",
            "Category": "Категории",
            "Favorite": "Избранное",
            "Response": "Отклики и разговоры",
            "Review": "Отзывы",
            "UserProfile": "Профили",
        }
        # Private marketplace messages are deliberately not exposed in the staff UI.
        for app in apps:
            if app["app_label"] == "ads":
                app["name"] = "Маркетплейс"
                app["models"] = [
                    model
                    for model in app["models"]
                    if model["object_name"] not in {"Favorite", "Response"}
                ]
                for model in app["models"]:
                    model["name"] = names.get(model["object_name"], model["name"])
            elif app["app_label"] == "auth":
                app["name"] = "Участники и доступ"
            elif app["app_label"] == "axes":
                app["name"] = "Защита входа"
            elif app["app_label"] == "token_blacklist":
                app["name"] = "Сессии приложения"
        priority = {"support": 0, "ads": 1, "auth": 2}
        apps.sort(key=lambda app: priority.get(app["app_label"], 3))
        return apps
