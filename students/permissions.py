from django.contrib.auth.decorators import login_required, permission_required

def can_edit(view):
    return login_required(permission_required("students.change_student", raise_exception=True)(view))

def can_add(view):
    return login_required(permission_required("students.add_student", raise_exception=True)(view))
