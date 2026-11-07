"""
WSGI config for distributed_system project.

It exposes the WSGI callable as a module-level variable named ``application``.
"""

import os
import sys
from pathlib import Path

# Add project root and web_gateway to sys.path so imports work in any environment
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent
ROOT_DIR = PROJECT_DIR.parent

for p in [str(PROJECT_DIR), str(ROOT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'distributed_system.settings')

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
app = application
