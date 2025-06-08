from django.contrib import admin
from .models import Ad, UserAdStat

@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = ('id', 'text', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('text',)

@admin.register(UserAdStat)
class UserAdStatAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'ads_shown', 'profiles_viewed', 'last_ad_shown_at')