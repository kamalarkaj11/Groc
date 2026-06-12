from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0015_product_api_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderAddress',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=128)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=15)),
                ('address_line1', models.TextField(blank=True)),
                ('address_line2', models.TextField(blank=True)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, choices=[
                    ('AP', 'Andhra Pradesh'),
                    ('TS', 'Telangana'),
                    ('MH', 'Maharashtra'),
                    ('AN', 'Andaman & Nicobar'),
                    ('AR', 'Arunachal Pradesh'),
                    ('AS', 'Assam'),
                    ('BR', 'Bihar'),
                    ('CH', 'Chandigarh'),
                    ('CT', 'Chhattisgarh'),
                    ('DN', 'Dadra & Nagar Haveli and Daman & Diu'),
                    ('DL', 'Delhi'),
                    ('GA', 'Goa'),
                    ('GJ', 'Gujarat'),
                    ('HR', 'Haryana'),
                    ('HP', 'Himachal Pradesh'),
                    ('JK', 'Jammu & Kashmir'),
                    ('JH', 'Jharkhand'),
                    ('KA', 'Karnataka'),
                    ('KL', 'Kerala'),
                    ('LA', 'Ladakh'),
                    ('MP', 'Madhya Pradesh'),
                    ('MN', 'Manipur'),
                    ('ML', 'Meghalaya'),
                    ('MZ', 'Mizoram'),
                    ('NL', 'Nagaland'),
                    ('OR', 'Odisha'),
                    ('PY', 'Puducherry'),
                    ('PB', 'Punjab'),
                    ('RJ', 'Rajasthan'),
                    ('SK', 'Sikkim'),
                    ('TN', 'Tamil Nadu'),
                    ('TR', 'Tripura'),
                    ('UP', 'Uttar Pradesh'),
                    ('UK', 'Uttarakhand'),
                    ('WB', 'West Bengal'),
                ], max_length=2)),
                ('postal_code', models.CharField(blank=True, max_length=10)),
                ('country', models.CharField(blank=True, default='India', max_length=64)),
                ('delivery_instructions', models.TextField(blank=True)),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.OneToOneField(on_delete=models.deletion.CASCADE, related_name='shipping_address', to='store.order')),
            ],
            options={
                'verbose_name': 'Order Address',
                'verbose_name_plural': 'Order Addresses',
            },
        ),
    ]
