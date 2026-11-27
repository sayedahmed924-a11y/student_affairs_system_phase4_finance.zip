from datetime import date

from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from .models import SystemAuditEvent


@login_required
@permission_required("students.view_systemauditevent", raise_exception=True)
def system_audit_list(request):
    events = SystemAuditEvent.objects.select_related("user").all()

    query = request.GET.get("q", "").strip()[:100]
    module = request.GET.get("module", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if query:
        events = events.filter(
            Q(actor_username__icontains=query)
            | Q(action__icontains=query)
            | Q(path__icontains=query)
            | Q(object_reference__icontains=query)
        )
    valid_modules = {value for value, _label in SystemAuditEvent.MODULES}
    if module in valid_modules:
        events = events.filter(module=module)
    try:
        if date_from:
            date.fromisoformat(date_from)
            events = events.filter(created_at__date__gte=date_from)
    except ValueError:
        date_from = ""
    try:
        if date_to:
            date.fromisoformat(date_to)
            events = events.filter(created_at__date__lte=date_to)
    except ValueError:
        date_to = ""

    paginator = Paginator(events, 100)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "students/system_audit.html", {
        "page_obj": page_obj,
        "events": page_obj.object_list,
        "query": query,
        "selected_module": module,
        "date_from": date_from,
        "date_to": date_to,
        "modules": SystemAuditEvent.MODULES,
        "total_count": paginator.count,
    })
