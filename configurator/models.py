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


class BraceletMaterial(models.TextChoices):
    ELASTIC_SILICONE = 'elastic_silicone', 'Elastic Silicone'
    METAL_CHAIN = 'metal_chain', 'Metal Chain'
    FABRIC_CORD = 'fabric_cord', 'Fabric Cord'


class BraceletBase(models.Model):
    name = models.CharField(max_length=100)
    material = models.CharField(
        max_length=20,
        choices=BraceletMaterial.choices,
        default=BraceletMaterial.ELASTIC_SILICONE,
    )
    total_slots = models.PositiveIntegerField()
    base_price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return self.name


class LeatherSize(models.TextChoices):
    SMALL = 'S', 'Small'
    MEDIUM = 'M', 'Medium'
    LARGE = 'L', 'Large'


class LeatherBraceletBase(models.Model):
    """A leather-cord-and-clasp bracelet type, structurally distinct from
    BraceletBase (not a subclass): the beaded segment sits within a fixed
    cord_image graphic rather than being rendered as a full CSS circle, and
    slot_count is a constant that does not vary by size (unlike
    BraceletBase.total_slots) - S/M/L still get separate rows here, same as
    BraceletBase, because cord_image and the segment offset/width differ per
    size even though slot_count doesn't.

    beaded_segment_offset_pct/width_pct are percentages of cord_image's width
    (not fixed px) so they stay correct if cord_image is re-exported at a
    different resolution per size - consistent with this project's convention
    of percentage/relative CSS sizing over fixed pixel math elsewhere.
    """

    name = models.CharField(max_length=100)
    size = models.CharField(max_length=1, choices=LeatherSize.choices)
    base_price = models.DecimalField(max_digits=8, decimal_places=2)
    slot_count = models.PositiveIntegerField()
    cord_image = models.ImageField(upload_to='leather_bracelet_bases/')
    beaded_segment_offset_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Distance from cord_image's left edge to the start of the beaded segment, as a % of image width.",
    )
    beaded_segment_width_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Width of the beaded segment within cord_image, as a % of image width.",
    )

    class Meta:
        ordering = ['size', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_size_display()})'


class BraceletConfiguration(models.Model):
    base = models.ForeignKey(
        BraceletBase,
        on_delete=models.PROTECT,
        related_name='configurations',
        null=True,
        blank=True,
    )
    leather_base = models.ForeignKey(
        LeatherBraceletBase,
        on_delete=models.PROTECT,
        related_name='configurations',
        null=True,
        blank=True,
    )
    session_key = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)
    is_finalized = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        chosen_base = self.base or self.leather_base
        return f'{chosen_base.name} config ({self.session_key})'


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
