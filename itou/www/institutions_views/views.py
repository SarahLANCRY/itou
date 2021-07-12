from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from itou.utils.perms.institution import get_current_institution_or_404


@login_required
def member_list(request, template_name="institutions/members.html"):
    """
    List members of a prescriber organization.
    """
    institution = get_current_institution_or_404(request)

    members = (
        institution.institutionmembership_set.filter(is_active=True)
        .select_related("user")
        .all()
        .order_by("-is_admin", "joined_at")
    )

    pending_invitations = None
    # Institution members can only be labor inspectors for the moment,
    # but this is likely to change in the future.
    if request.user.is_labor_inspector:
        pending_invitations = institution.labor_inspectors_invitations.pending()

    context = {
        "institution": institution,
        "members": members,
        "pending_invitations": pending_invitations,
    }
    return render(request, template_name, context)
