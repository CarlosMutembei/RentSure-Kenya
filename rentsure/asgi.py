import os
import django
from django.core.asgi import get_asgi_application

# 1. Establish the core settings profile pointer
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rentsure.settings')

# 2. Force Django registry mapping to spin up cleanly first
django.setup()

# 3. Initialize the core HTTP ASGI framework app layer
django_asgi_app = get_asgi_application()

# 4. NOW it is safe to import Channels components and app routing variables
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from properties.routing import websocket_urlpatterns

# 5. Define your master system protocol routing table
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})