=== DRY RUN start: 2026-09-17 13:54:01 UTC ===
creating venv...
The virtual environment was not created successfully because ensurepip is not
available.  On Debian/Ubuntu systems, you need to install the python3-venv
package using the following command.

    apt install python3.12-venv

You may need to use sudo with that command.  After installing the python3-venv
package, recreate your virtual environment.

Failing command: /home/manouka/web/libertidance.com/import-bundle/.venv/bin/python3

venv failed — will try pip --user
/home/manouka/web/libertidance.com/import-bundle/run-dry-run.sh: line 19: .venv/bin/pip: No such file or directory
INFO    log file: logs/import-2026-09-17-165401.log
INFO    CSV OK: 1 row(s) to process
ERROR   database connection failed: No module named 'pymysql'
=== DRY RUN end (exit 2): 2026-09-17 13:54:01 UTC ===
IMPORTANT: review every plan line in dryrun-out.txt. Nothing has been written.
=== DRY RUN start: 2026-09-17 14:24:01 UTC ===
server python: Python 3.12.3
INFO    log file: logs/import-2026-09-17-172401.log
INFO    CSV OK: 1 row(s) to process
INFO    read-only connection (dry-run): write statements are blocked by the application and by the server
INFO    --------------------------------------------------------------
INFO    SKU: 0405PT
INFO    Operation: CREATE
INFO      [INSERT_CORE ] virtuemart_products: core row (published=0, gtin=sku)
INFO      [INSERT_LANG ] virtuemart_products_en_gb: name='Brushed Tights 0405PT', description (110 chars), slug='brushed-tights-0405pt'
INFO      [INSERT_LANG ] virtuemart_products_el_gr: name='Brushed Κολάν 0405PT', description (102 chars), slug='brushed-tights-0405pt'
INFO      [INSERT_PRICE] virtuemart_product_prices: net price 20.08 (tax rule 1, EUR, shoppergroup 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Size = '36' (custom 6, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Size = '38' (custom 6, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Size = '40' (custom 6, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Size = '42' (custom 6, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Size = '44' (custom 6, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Colour = 'BLK' (custom 7, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Colour = 'NAVY' (custom 7, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Colour = 'BORDEAUX' (custom 7, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Colour = 'GREY' (custom 7, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Colour = 'GREY PINK' (custom 7, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Colour = 'ICE BLUE' (custom 7, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Colour = 'LAGUNA' (custom 7, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Colour = 'MIRTILLO' (custom 7, price 0, published 0)
INFO      [INSERT_CF   ] virtuemart_product_customfields: Colour = 'ORCHID MIST' (custom 7, price 0, published 0)
INFO      [INSERT_MEDIA] virtuemart_medias: '0405 PT Orchid Mist.jpg' (image/jpeg), file_meta = EN title (main image)
INFO      [INSERT_MEDIA] virtuemart_medias: '0405PT Black.jpg' (image/jpeg)
INFO      [INSERT_MEDIA] virtuemart_medias: '0405PT Blue.jpg' (image/jpeg)
INFO      [INSERT_MEDIA] virtuemart_medias: '0405PT Bordeaux.jpg' (image/jpeg)
INFO      [INSERT_MEDIA] virtuemart_medias: '0405PT Grey Pink.jpg' (image/jpeg)
INFO      [INSERT_MEDIA] virtuemart_medias: '0405PT Grey.jpg' (image/jpeg)
INFO      [INSERT_MEDIA] virtuemart_medias: '0405PT Ice Blue.jpg' (image/jpeg)
INFO      [INSERT_MEDIA] virtuemart_medias: '0405PT Laguna.jpg' (image/jpeg)
INFO      [INSERT_MEDIA] virtuemart_medias: '0405PT Mirtillo.jpg' (image/jpeg)
INFO      [INSERT_LINK ] virtuemart_product_medias: link ordering 1: 0405 PT Orchid Mist.jpg
INFO      [INSERT_LINK ] virtuemart_product_medias: link ordering 2: 0405PT Black.jpg
INFO      [INSERT_LINK ] virtuemart_product_medias: link ordering 3: 0405PT Blue.jpg
INFO      [INSERT_LINK ] virtuemart_product_medias: link ordering 4: 0405PT Bordeaux.jpg
INFO      [INSERT_LINK ] virtuemart_product_medias: link ordering 5: 0405PT Grey Pink.jpg
INFO      [INSERT_LINK ] virtuemart_product_medias: link ordering 6: 0405PT Grey.jpg
INFO      [INSERT_LINK ] virtuemart_product_medias: link ordering 7: 0405PT Ice Blue.jpg
INFO      [INSERT_LINK ] virtuemart_product_medias: link ordering 8: 0405PT Laguna.jpg
INFO      [INSERT_LINK ] virtuemart_product_medias: link ordering 9: 0405PT Mirtillo.jpg
INFO    --------------------------------------------------------------
INFO    DRY RUN (no changes were made)
=== DRY RUN end (exit 0): 2026-09-17 14:24:01 UTC ===
IMPORTANT: review every plan line in dryrun-out.txt. Nothing has been written.
=== DRY RUN start: 2026-09-21 07:16:01 UTC ===
server python: Python 3.12.3
INFO    log file: logs/import-2026-09-21-101602.log
INFO    CSV OK: 2 row(s) to process
INFO    read-only connection (dry-run): write statements are blocked by the application and by the server
INFO    --------------------------------------------------------------
INFO    SKU: 102
INFO    Operation: CREATE
INFO      [INSERT_CORE ] virtuemart_products: core row (published=0, gtin=sku)
INFO      [INSERT_LANG ] virtuemart_products_en_gb: name='102 Glisse', description (69 chars), slug='102-glisse'
INFO      [INSERT_LANG ] virtuemart_products_el_gr: name='102 Glisse', description (60 chars), slug='102-glisse'
INFO      [INSERT_PRICE] virtuemart_product_prices: net price 20.16129 = display 25.00 EUR incl. 24% VAT (tax rule 1, EUR, shoppergroup 0)
INFO      [INSERT_MEDIA] virtuemart_medias: '102 Glisse.jpg' (image/jpeg), file_meta = EN title (main image)
INFO      [INSERT_LINK ] virtuemart_product_medias: link ordering 1: 102 Glisse.jpg
INFO    --------------------------------------------------------------
INFO    SKU: 1130
INFO    Operation: CREATE
INFO      [INSERT_CORE ] virtuemart_products: core row (published=0, gtin=sku)
INFO      [INSERT_LANG ] virtuemart_products_en_gb: name='1130 Airess', description (69 chars), slug='1130-airess'
INFO      [INSERT_LANG ] virtuemart_products_el_gr: name='1130 Airess', description (60 chars), slug='1130-airess'
INFO      [INSERT_PRICE] virtuemart_product_prices: net price 24.193548 = display 30.00 EUR incl. 24% VAT (tax rule 1, EUR, shoppergroup 0)
INFO      [INSERT_MEDIA] virtuemart_medias: '1130 Airess.jpg' (image/jpeg), file_meta = EN title (main image)
INFO      [INSERT_LINK ] virtuemart_product_medias: link ordering 1: 1130 Airess.jpg
INFO    --------------------------------------------------------------
INFO    DRY RUN (no changes were made)
=== DRY RUN end (exit 0): 2026-09-21 07:16:02 UTC ===
IMPORTANT: review every plan line in dryrun-out.txt. Nothing has been written.
