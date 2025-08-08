from django.contrib import admin
from .models import Ad, UserAdStat, UserAdView

@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = ('id', 'text', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('text',)

@admin.register(UserAdStat)
class UserAdStatAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'ads_shown', 'profiles_viewed', 'last_ad_shown_at')

@admin.register(UserAdView)  # Регистрируем новую модель
class UserAdViewAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'ad', 'viewed_at')  # Поля для отображения в списке
    list_filter = ('viewed_at', 'ad')  # Фильтры
    search_fields = ('user_id',)  # Поиск по ID пользователя
    date_hierarchy = 'viewed_at'  # Иерархия по дате