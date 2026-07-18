from django.db import models


class ItemCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name_plural = 'item categories'

    def __str__(self):
        return self.name


class BraceletItem(models.Model):
    category = models.ForeignKey(
        ItemCategory, on_delete=models.PROTECT, related_name='items'
    )
    name = models.CharField(max_length=100)
    material = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    image = models.ImageField(upload_to='bracelet_items/')
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    slot_width = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


class BraceletBase(models.Model):
    name = models.CharField(max_length=100)
    total_slots = models.PositiveIntegerField()
    base_price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return self.name


class BraceletConfiguration(models.Model):
    base = models.ForeignKey(
        BraceletBase, on_delete=models.PROTECT, related_name='configurations'
    )
    session_key = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)
    is_finalized = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.base.name} config ({self.session_key})'


class BraceletConfigurationItem(models.Model):
    """One row per physical bead/charm placed on a configuration, not a quantity count."""

    configuration = models.ForeignKey(
        BraceletConfiguration, on_delete=models.CASCADE, related_name='items'
    )
    item = models.ForeignKey(
        BraceletItem, on_delete=models.PROTECT, related_name='configuration_items'
    )
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ['position']
        constraints = [
            models.UniqueConstraint(
                fields=['configuration', 'position'],
                name='unique_position_per_configuration',
            )
        ]

    def __str__(self):
        return f'{self.item.name} @ {self.position}'
