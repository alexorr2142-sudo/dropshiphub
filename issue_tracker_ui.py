"""Issue tracker UI facade.

Constraint: keep files small (<300 lines).
"""

from __future__ import annotations

from core.issue_tracker_apply import apply_issue_tracker
from ui.issue_tracker_maintenance_ui import render_issue_tracker_maintenance
from ui.issue_tracker_ownership_ui import render_issue_ownership_panel
from ui.issue_tracker_panel_ui import render_issue_tracker_panel
