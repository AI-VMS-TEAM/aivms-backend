from .auth_routes import auth_bp, token_required, admin_required
from .tenant_routes import tenant_bp
from .event_routes import event_bp
from .edge_routes import edge_bp

__all__ = [
    'auth_bp',
    'tenant_bp', 
    'event_bp',
    'edge_bp',
    'token_required',
    'admin_required'
]
