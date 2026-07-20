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


class LeatherSize(models.TextChoices):
    SMALL = 'S', 'Small'
    MEDIUM = 'M', 'Medium'
    LARGE = 'L', 'Large'


class LeatherBraceletBase(models.Model):
    """A leather-cord bracelet type, structurally distinct from BraceletBase
    (not a subclass) only in how its live-builder circle is drawn - beads
    render exactly like BraceletBase's (same BraceletItem.image, same
    rotate()/translate() placement, same fixed 72px + slot-N sizing), just
    constrained to a sub-arc centered at the top instead of the full 360,
    with a plain-CSS clasp marker at the bottom completing the circle. No
    photo is involved in this rendering path - cord_image is unused here,
    reserved for a later checkout-time Pillow composite.

    slot_count varies by size/row here, same as BraceletBase.total_slots
    (reversing an earlier, later-reverted "fixed across sizes" design).

    Arc geometry is computed, not stored - see ARC_CENTER_DEG and
    arc_span_deg below. --radius is NOT computed per-row: the live-builder
    template reuses BraceletBase's own --radius clamp() formula unmodified
    (105px + 5px/slot, capped 255px) rather than a leather-specific one,
    since arc_span_deg is what adapts to slot_count - see arc_span_deg's
    docstring for why coupling both to slot_count blows the arc past 360
    degrees for realistic slot counts.
    """

    ARC_CENTER_DEG = 90  # 12 o'clock - 0deg=3 o'clock, increasing
    # counter-clockwise (same convention/rotate-sign-flip as build_tray.html
    # uses for BraceletBase's circle, just negated so 90deg lands at the
    # top instead of the circle's own native 3-o'clock-clockwise reading).

    name = models.CharField(max_length=100)
    size = models.CharField(max_length=1, choices=LeatherSize.choices)
    base_price = models.DecimalField(max_digits=8, decimal_places=2)
    slot_count = models.PositiveIntegerField()
    cord_image = models.ImageField(
        upload_to='leather_bracelet_bases/',
        blank=True,
        null=True,
        help_text='Not used by the live builder. Reserved for a future checkout-time composite image.',
    )

    class Meta:
        ordering = ['size', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_size_display()})'

    @property
    def arc_span_deg(self):
        """clamp(70, 50 + slot_count * 13, 230), in degrees.

        Deliberately NOT tuned to hold bead spacing exactly constant as
        slot_count grows - doing that against BraceletBase's own slow-growing
        --radius (+5px/slot) requires the span to grow super-linearly and it
        blows past 360deg well before slot_count=9. This formula instead
        keeps spacing in a stable ~48-62px band across slot_count 3-14
        (checked by hand against the unmodified BraceletBase radius formula)
        rather than letting it degrade as capacity grows, which is what the
        earlier fixed-radius design did.
        """
        return min(max(50 + self.slot_count * 13, 70), 230)

    @property
    def arc_start_deg(self):
        return self.ARC_CENTER_DEG - self.arc_span_deg / 2

    @property
    def arc_end_deg(self):
        return self.ARC_CENTER_DEG + self.arc_span_deg / 2


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
