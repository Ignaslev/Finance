from .dashboard import overview, home, env_check
from .transactions import (
    tx_add, tx_edit, tx_delete, tx_restore, upload, uncategorized,
    tx_bulk_category_apply, deleted_list
)
from .assets import (
    assets_dashboard, asset_add, asset_edit, api_search_asset
)
from .reports import statistics, reports, reports_generate
from .settings import (
    profile, register, category_list, category_edit, category_delete,
    onboarding_mark_done, profile_delete_account, profile_cancel_delete_account
)
# UNCOMMENTED THESE LINES:
from .ai import (
   ai_full_categorize, ai_run_uncategorized, ai_recheck_all,
   teach_ai, review_low_conf, review_low_apply, review_ai_recent,
   ai_dismiss_notification, review_ai_runs, review_ai_run_detail
)