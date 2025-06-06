from flask_admin.contrib.sqla import ModelView
from admin.models import Ad, UserAdStat
from admin import admin, db

admin.add_view(ModelView(Ad, db.session))
admin.add_view(ModelView(UserAdStat, db.session))