"""Generated migration for InvoiceHistory model."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0035_alter_order_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='InvoiceHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('invoice_number', models.CharField(max_length=50, help_text='Auto-generated invoice number')),
                ('invoice_type', models.CharField(choices=[('original', 'Original'), ('regenerated', 'Regenerated')], default='original', max_length=20, help_text='Type of invoice generation')),
                ('generated_by', models.CharField(blank=True, max_length=100, help_text='Who generated this invoice')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, help_text='Optional notes about this invoice generation')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoice_history', to='store.order')),
            ],
            options={
                'verbose_name': 'Invoice History',
                'verbose_name_plural': 'Invoice Histories',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['order', '-created_at'], name='store_inv_order_i_8a6e3f_idx'),
                    models.Index(fields=['invoice_number'], name='store_inv_invoice_1b5e1e_idx'),
                ],
            },
        ),
    ]