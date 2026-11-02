import os
import sys

import django

ROOT = os.path.dirname(os.path.abspath(__file__))
ADMIN_DIR = os.path.join(ROOT, "gymbros_admin")

# ADMIN_DIR первым: отсюда импортируются botapp и gymbros_admin.settings
sys.path.insert(0, ROOT)
sys.path.insert(0, ADMIN_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gymbros_admin.settings")
django.setup()

from bot.core import main

if __name__ == "__main__":
    main()
