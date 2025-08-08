from django.db import models

class Ad(models.Model):
    text = models.TextField()
    image = models.ImageField(upload_to='ads/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    telegram_file_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Ad {self.id}"

class UserAdStat(models.Model):
    user_id = models.BigIntegerField(primary_key=True)
    ads_shown = models.IntegerField(default=0)
    profiles_viewed = models.IntegerField(default=0)
    last_ad_shown_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"UserAdStat {self.user_id}"
    
class UserAdView(models.Model):
    user_id = models.BigIntegerField()
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user_id', 'ad')  # Гарантирует уникальность пары user_id + ad