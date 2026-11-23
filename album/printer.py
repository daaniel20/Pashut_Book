"""The printer's file rules (task 2.3).

Everything the printer asks of the print file is here, as settings, so a new
printer (a local printer, Lupa, Prodigi) means changing only this file.
The page size itself is in designs.py (PAGE_WIDTH, PAGE_HEIGHT).

⚠️ These are common values, placeholders until the printer is chosen (task S.2).
Ask the printer for: page size, bleed, resolution, colour (RGB or CMYK),
one file or a separate cover, which side the book is bound on, and the cover
size (a hardcover's cover wraps around the board and has a spine).
"""

# Bleed: extra picture around each page that the printer cuts off, so there is
# never a thin white line at the edge. Photos and colours that reach the edge
# are drawn 3 mm further. 3 mm is the most common rule.
BLEED = 3            # mm, inside pages
COVER_BLEED = 3      # mm, the cover (a hardcover wrap often needs 15-20 mm)

# Resolution: 300 dots per inch (DPI) is the print standard.
DPI = 300
JPEG_QUALITY = 95    # the pages are stored as high-quality JPEG inside the PDF

# A photo printed with fewer dots per inch than this gets a warning for the owner.
GOOD_DPI = 200       # 200+ looks fine in print
LOW_DPI = 150        # below this it looks blurry: replace the photo

# The cover in its own file (most printers), or as page 1 of the same file.
COVER_SEPARATE = True

# Hebrew books are bound on the RIGHT. The PDF keeps the reading order
# (page 1, 2, 3 …). Tell the printer it's a right-bound book. A printer that
# binds on the left only (e.g. Prodigi) needs the pages in reverse order:
# see docs/research-notes.md, add it here when such a printer is chosen.
BINDING = "right"
