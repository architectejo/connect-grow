"""Avis après contact (ADR 0004, L0-07) : retrait de `Deal` et de `TrustScoreSettings`, nouveau
modèle `Review` (deux notes, preuve de contact), réglages `ReviewSettings`.

`Review` est supprimé puis recréé : aucune donnée de production n'existe (ADR 0002) et les anciens
avis, fondés sur une « affaire conclue », n'ont ni preuve de contact ni note vendeur. La table
`ReviewDailyCount` est conservée. Le `0001` n'est pas réécrit (CLAUDE.md §9).
"""
from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import uuid

import apps.reviews.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reviews', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(name='Review'),
        migrations.DeleteModel(name='Deal'),
        migrations.DeleteModel(name='TrustScoreSettings'),
        migrations.CreateModel(
            name='ReviewSettings',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('min_reviews_to_display', models.PositiveIntegerField(default=3, help_text="Nombre d'avis à partir duquel une moyenne est affichée.", validators=[django.core.validators.MinValueValidator(1)])),
                ('daily_review_limit', models.PositiveIntegerField(default=5, help_text='Avis maximum par utilisateur et par jour.', validators=[django.core.validators.MinValueValidator(1)])),
                ('edit_window_hours', models.PositiveIntegerField(default=48, help_text='Heures pendant lesquelles un avis reste modifiable.', validators=[django.core.validators.MinValueValidator(1)])),
                ('delay_after_contact_hours', models.PositiveIntegerField(default=24, help_text="Heures à attendre entre le contact et l'avis (0 : aucun délai).")),
                ('crossed_reviews_window_days', models.PositiveIntegerField(default=30, help_text='Fenêtre de détection des avis croisés, en jours.', validators=[django.core.validators.MinValueValidator(1)])),
                ('crossed_reviews_threshold', models.PositiveIntegerField(default=3, help_text="Nombre d'avis entre les deux mêmes comptes qui déclenche un signalement automatique.", validators=[django.core.validators.MinValueValidator(2)])),
            ],
            options={
                'verbose_name': 'Paramètres des avis',
                'verbose_name_plural': 'Paramètres des avis',
            },
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('offer_id', models.UUIDField(db_index=True)),
                ('seller_context_type', models.CharField(choices=[('USER', 'Compte personnel'), ('ORGANIZATION', 'Organisation')], default='USER', max_length=20)),
                ('seller_context_id', models.UUIDField()),
                ('contact_event_id', models.UUIDField()),
                ('contact_channel', models.CharField(max_length=10)),
                ('contact_recorded_at', models.DateTimeField()),
                ('offer_rating', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('seller_rating', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('content', models.TextField(validators=[apps.reviews.models._validate_content_length])),
                ('reply_content', models.TextField(blank=True, null=True, validators=[django.core.validators.MaxLengthValidator(500)])),
                ('reply_at', models.DateTimeField(blank=True, null=True)),
                ('is_hidden', models.BooleanField(default=False)),
                ('counts_for_seller', models.BooleanField(default=True)),
                ('edited_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews_written', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['seller_context_type', 'seller_context_id', 'is_hidden', 'counts_for_seller'], name='review_seller_avg'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['offer_id', 'is_hidden'], name='review_offer_avg'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['user', 'seller_context_id', 'created_at'], name='review_author_seller'),
        ),
        migrations.AddConstraint(
            model_name='review',
            constraint=models.UniqueConstraint(fields=('user', 'offer_id'), name='uniq_review_author_offer'),
        ),
    ]
