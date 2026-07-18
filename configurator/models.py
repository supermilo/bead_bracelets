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
    BraceletBase (not a subclass): beads sit along a partial arc within a
    fixed cord_image graphic (cord crosses at a clasp above the arc) rather
    than being rendered as a full CSS circle, and slot_count is a constant
    that does not vary by size (unlike BraceletBase.total_slots) - S/M/L
    still get separate rows here, same as BraceletBase, because cord_image
    and the arc geometry differ per size even though slot_count doesn't.

    beaded_arc_start_deg/end_deg/bead_orbit_radius_pct describe that arc in
    the same degree convention build_tray.html's rotate()/translate() bead
    placement uses: 0deg = 3 o'clock, increasing counter-clockwise, so
    90deg = 12 o'clock (where the clasp sits), 270deg = 6 o'clock (bottom
    center of the arc). A symmetric bottom arc is centered on 270deg, e.g.
    start=215/end=325 spans 55deg either side of dead-bottom.
    bead_orbit_radius_pct is a % of cord_image's *shorter* dimension (its
    height, for a typical wide bracelet-lying-flat photo) rather than width -
    since the arc droops down from center, sizing the radius off the
    narrower axis is what actually keeps beads inside the image at the
    bottom of the sweep; sizing off width would overflow beneath a short,
    wide image. Percentage-based (not fixed px) so it stays correct if
    cord_image is re-exported at a different resolution per size, consistent
    with this project's preference for relative over fixed-px CSS sizing.

    The 215/325/27 defaults were verified against a real reference photo
    (679x230px, ~3:1) by measuring actual rendered bead positions in a
    browser, not just eyeballed - the originally-approved 200/340/32 looked
    right on paper but its larger radius pushed beads below the image once
    real beads were rendered, since radius is bottlenecked by the image's
    short dimension (a bigger radius means more vertical droop at dead-
    bottom, not just more horizontal spread). These are still just a
    starting point for a differently-proportioned cord_image.
    """

    name = models.CharField(max_length=100)
    size = models.CharField(max_length=1, choices=LeatherSize.choices)
    base_price = models.DecimalField(max_digits=8, decimal_places=2)
    slot_count = models.PositiveIntegerField()
    cord_image = models.ImageField(upload_to='leather_bracelet_bases/')
    beaded_arc_start_deg = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=215,
        help_text="Arc start angle: 0deg = 3 o'clock, increasing counter-clockwise (90deg = 12 o'clock, 270deg = 6 o'clock).",
    )
    beaded_arc_end_deg = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=325,
        help_text="Arc end angle, same convention as beaded_arc_start_deg.",
    )
    bead_orbit_radius_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=27,
        help_text="Bead orbit radius as a % of cord_image's shorter dimension (its height, typically).",
    )

    class Meta:
        ordering = ['size', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_size_display()})'

    @property
    def arc_span_deg(self):
        """Django templates can't subtract two variables inline, and
        build_tray.html needs this span as a single number to feed
        {% widthratio %}'s max_width argument - see the template for how
        the per-bead angle is assembled from this."""
        return self.beaded_arc_end_deg - self.beaded_arc_start_deg


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
