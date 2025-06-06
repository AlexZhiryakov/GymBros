from admin import db

class Ad(db.Model):
    __tablename__ = 'ads'  # Соответствует вашей SQL-таблице
    
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.now())

class UserAdStat(db.Model):
    __tablename__ = 'user_ad_stats'
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    ads_shown = db.Column(db.Integer, default=0)
    profiles_viewed = db.Column(db.Integer, default=0)
    last_ad_shown_at = db.Column(db.TIMESTAMP)