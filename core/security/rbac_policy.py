from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional


class UserRole(str, Enum):
    STUDENT = "student"
    FACULTY = "faculty"
    LIBRARIAN = "librarian"
    ADMIN = "admin"

    @classmethod
    def normalize(cls, raw_role: Optional[str]) -> "UserRole":
        if not raw_role or not isinstance(raw_role, str):
            return cls.STUDENT
        cleaned = raw_role.strip().lower()
        for member in cls:
            if member.value == cleaned:
                return member
        return cls.STUDENT


class Permission(str, Enum):
    # Circulation & Borrowing
    BORROW_BOOKS = "borrow_books"
    RENEW_OWN_LOAN = "renew_own_loan"
    OPERATE_CIRCULATION_DESK = "operate_circulation_desk"

    # Curricular Requisitions (Form FM-LIBS-002)
    SUBMIT_REQUISITION_FM_LIBS_002 = "submit_requisition_fm_libs_002"
    REVIEW_REQUISITION_FM_LIBS_002 = "review_requisition_fm_libs_002"

    # Collection & Catalog Control
    INGEST_AND_EDIT_CATALOG = "ingest_and_edit_catalog"
    PURGE_CATALOG_TITLES = "purge_catalog_titles"

    # Campus Attendance & Gate Logging (Form FM-LIBS-009)
    SCAN_ATTENDANCE_PASS = "scan_attendance_pass"
    OPERATE_GATE_TERMINAL = "operate_gate_terminal"
    VIEW_EXPORT_FM_LIBS_009 = "view_export_fm_libs_009"
    VIEW_LIVE_DOORWAY_STREAM = "view_live_doorway_stream"

    # OPDS E-Reader Feed
    READ_OPDS_FEED = "read_opds_feed"
    MANAGE_OPDS_HUB = "manage_opds_hub"

    # Analytics & AI Workstation
    VIEW_CURRICULAR_ANALYTICS = "view_curricular_analytics"
    VIEW_ACCREDITATION_FOOT_TRAFFIC = "view_accreditation_foot_traffic"
    USE_TARS_AI_WORKSTATION = "use_tars_ai_workstation"

    # Root IT Governance (Admin Only)
    MANAGE_RBAC_USERS = "manage_rbac_users"
    MANAGE_CHROMADB_VECTORS = "manage_chromadb_vectors"
    VIEW_INFRASTRUCTURE_DIAGNOSTICS = "view_infrastructure_diagnostics"


@dataclass(frozen=True)
class RoleCirculationPolicy:
    role: UserRole
    display_label: str
    badge_icon: str
    max_active_loans: int
    loan_duration_days: int
    renewal_extension_days: int
    max_renewals_per_loan: int
    can_override_loans: bool
    is_staff: bool


CIRCULATION_POLICIES: Dict[UserRole, RoleCirculationPolicy] = {
    UserRole.STUDENT: RoleCirculationPolicy(
        role=UserRole.STUDENT,
        display_label="Student",
        badge_icon="🎓",
        max_active_loans=3,
        loan_duration_days=7,
        renewal_extension_days=7,
        max_renewals_per_loan=1,
        can_override_loans=False,
        is_staff=False,
    ),
    UserRole.FACULTY: RoleCirculationPolicy(
        role=UserRole.FACULTY,
        display_label="Faculty Member",
        badge_icon="👨‍🏫",
        max_active_loans=10,
        loan_duration_days=30,
        renewal_extension_days=15,
        max_renewals_per_loan=2,
        can_override_loans=False,
        is_staff=False,
    ),
    UserRole.LIBRARIAN: RoleCirculationPolicy(
        role=UserRole.LIBRARIAN,
        display_label="University Librarian",
        badge_icon="📚",
        max_active_loans=25,
        loan_duration_days=30,
        renewal_extension_days=15,
        max_renewals_per_loan=99,
        can_override_loans=True,
        is_staff=True,
    ),
    UserRole.ADMIN: RoleCirculationPolicy(
        role=UserRole.ADMIN,
        display_label="System Administrator",
        badge_icon="🛡️",
        max_active_loans=50,
        loan_duration_days=30,
        renewal_extension_days=30,
        max_renewals_per_loan=99,
        can_override_loans=True,
        is_staff=True,
    ),
}


ROLE_PERMISSIONS: Dict[UserRole, FrozenSet[Permission]] = {
    UserRole.STUDENT: frozenset(
        {
            Permission.BORROW_BOOKS,
            Permission.RENEW_OWN_LOAN,
            Permission.SCAN_ATTENDANCE_PASS,
            Permission.READ_OPDS_FEED,
            Permission.USE_TARS_AI_WORKSTATION,
        }
    ),
    UserRole.FACULTY: frozenset(
        {
            Permission.BORROW_BOOKS,
            Permission.RENEW_OWN_LOAN,
            Permission.SUBMIT_REQUISITION_FM_LIBS_002,
            Permission.SCAN_ATTENDANCE_PASS,
            Permission.READ_OPDS_FEED,
            Permission.VIEW_CURRICULAR_ANALYTICS,
            Permission.USE_TARS_AI_WORKSTATION,
        }
    ),
    UserRole.LIBRARIAN: frozenset(
        {
            Permission.BORROW_BOOKS,
            Permission.RENEW_OWN_LOAN,
            Permission.OPERATE_CIRCULATION_DESK,
            Permission.REVIEW_REQUISITION_FM_LIBS_002,
            Permission.INGEST_AND_EDIT_CATALOG,
            Permission.PURGE_CATALOG_TITLES,
            Permission.SCAN_ATTENDANCE_PASS,
            Permission.OPERATE_GATE_TERMINAL,
            Permission.VIEW_EXPORT_FM_LIBS_009,
            Permission.READ_OPDS_FEED,
            Permission.MANAGE_OPDS_HUB,
            Permission.VIEW_CURRICULAR_ANALYTICS,
            Permission.VIEW_ACCREDITATION_FOOT_TRAFFIC,
            Permission.USE_TARS_AI_WORKSTATION,
        }
    ),
    # Admin has full universal operational access across all tiers
    UserRole.ADMIN: frozenset(Permission),
}


def get_circulation_policy(user_or_role: Any) -> RoleCirculationPolicy:
    """Returns the immutable circulation quota policy for a user dict or role string."""
    if isinstance(user_or_role, dict):
        role = UserRole.normalize(user_or_role.get("role"))
    elif isinstance(user_or_role, UserRole):
        role = user_or_role
    else:
        role = UserRole.normalize(str(user_or_role) if user_or_role else None)
    return CIRCULATION_POLICIES[role]


def has_permission(user_or_role: Any, permission: Permission) -> bool:
    """Checks if a user dict or role string possesses a specific Permission."""
    policy = get_circulation_policy(user_or_role)
    return permission in ROLE_PERMISSIONS[policy.role]


def require_permission(user_or_role: Any, permission: Permission) -> None:
    """
    Server-side guard that raises PermissionError with an explicit role explanation
    if an unauthorized account attempts a restricted action.
    """
    policy = get_circulation_policy(user_or_role)
    if permission not in ROLE_PERMISSIONS[policy.role]:
        raise PermissionError(
            f"Access Denied: Role '{policy.display_label}' ({policy.role.value}) "
            f"does not have permission '{permission.value}'."
        )


def get_allowed_routes_for_role(user_or_role: Any) -> List[Dict[str, str]]:
    """
    Returns the ordered navigation menu items permitted for the given user role.
    """
    policy = get_circulation_policy(user_or_role)
    role = policy.role

    routes = [
        {"path": "/books", "label": "📖 Library Catalog", "group": "Academic"},
        {"path": "/chat", "label": "🤖 TARS AI Workstation", "group": "Academic"},
        {"path": "/planner", "label": "🗂️ Study Planner & Decks", "group": "Academic"},
        {"path": "/summarizer", "label": "📝 Chapter Summarizer", "group": "Academic"},
        {"path": "/attendance", "label": "🪪 Attendance & QR Pass", "group": "Campus"},
        {"path": "/profile", "label": "👤 My Profile & Loans", "group": "Account"},
    ]

    if has_permission(role, Permission.SUBMIT_REQUISITION_FM_LIBS_002):
        routes.append(
            {
                "path": "/requisitions",
                "label": "📑 Book Requisitions (FM-LIBS-002)",
                "group": "Faculty",
            }
        )

    if has_permission(role, Permission.OPERATE_CIRCULATION_DESK):
        routes.extend(
            [
                {
                    "path": "/librarian",
                    "label": "📚 Librarian Operations Console",
                    "group": "Operations",
                },
                {
                    "path": "/upload",
                    "label": "⬆️ Book Ingestion & Upload",
                    "group": "Operations",
                },
            ]
        )

    if (
        has_permission(role, Permission.VIEW_CURRICULAR_ANALYTICS)
        or has_permission(role, Permission.VIEW_ACCREDITATION_FOOT_TRAFFIC)
    ):
        routes.append(
            {
                "path": "/analytics",
                "label": "📊 Institutional Analytics",
                "group": "Operations",
            }
        )

    if has_permission(role, Permission.MANAGE_RBAC_USERS):
        routes.append(
            {
                "path": "/admin",
                "label": "🛡️ Admin IT Governance",
                "group": "Governance",
            }
        )

    return routes
