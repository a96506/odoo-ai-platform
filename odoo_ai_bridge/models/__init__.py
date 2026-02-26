from . import ai_config
from . import ai_webhook_mixin
from . import account_move
from . import crm_lead
from . import sale_order
from . import purchase_order
from . import stock_picking
from . import hr_leave
from . import hr_expense
from . import project_task
from . import mrp_production
from . import mailing_mailing

try:
    from . import helpdesk_ticket
except ImportError:
    pass
