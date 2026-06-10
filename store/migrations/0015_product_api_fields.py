from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0014_subsubcategory_product_subsubcategory_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='api_payload',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='product',
            name='api_product_id',
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name='product',
            name='api_rating',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='api_review_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='product',
            name='api_source',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='product',
            name='availability',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='product',
            name='external_image_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['api_source', 'api_product_id'], name='store_produ_api_sou_3fd3fc_idx'),
        ),
    ]
