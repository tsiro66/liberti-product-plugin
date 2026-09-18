Now move from the database reverse-engineering phase to IMPLEMENTING the actual importer.

You have already completed the investigation of this Joomla 5.4.8 + VirtueMart 4.8.0 database and produced the database analysis. Do NOT repeat the reverse-engineering phase unless you encounter an inconsistency while implementing.

Your task now is to build a reusable Python product importer based on the actual database structure you discovered.

IMPORTANT:
- The importer must NOT use the old CSV importer.
- It must NOT depend on Joomla/VirtueMart HTTP APIs.
- It will write directly to the MariaDB database.
- It must be designed carefully around the exact schema discovered in the previous phase.
- Do not invent VirtueMart behavior. Use the analysis and the SQL dump as the source of truth.
- Do not modify the production database while developing/testing.
- Build the importer so that it can initially run in DRY-RUN mode and show exactly what it would change.
- Never make destructive changes unless explicitly enabled.
- Imported products must default to published=0.

## INPUT

The importer should accept a CSV file and a local images directory.

The CSV needs to contain at minimum:

- sku
- title_en
- description_en
- title_el
- description_el
- price
- sizes
- colours
- fabric

You may choose a practical CSV representation for multiple values, for example:

sizes:
35|36|37|38|39|40|41|42

colours:
BLK|RED

fabric:
Leather

Document the exact CSV format you choose.

Images are stored locally in:

./images/

Most image filenames correspond to the SKU, for example:

0405PT Black.jpg

means SKU:

0405PT

The filename may contain additional descriptive text after the SKU. Build robust SKU matching rather than assuming the entire filename is the SKU.

If multiple images belong to one SKU, all matching images should be imported in deterministic order.

## FIRST: IMPLEMENTATION PLAN

Before writing code:

1. Read your previously generated `virtuemart-database-analysis.md`.
2. Inspect the existing project directory.
3. Inspect the SQL dump again if necessary.
4. Produce a short implementation plan based on the exact schema you discovered.
5. Then implement the importer.

Do not ask me to manually provide table names that you already discovered.

## ARCHITECTURE

Build this as a maintainable Python application, NOT as one giant script.

Use clear separation such as:

- configuration
- CSV parsing/validation
- database/repository layer
- product importer/service
- custom field handling
- media/image handling
- transaction handling
- logging/reporting
- CLI

Choose sensible filenames/package structure.

Use a proper MariaDB/MySQL Python driver.

Database credentials MUST come from environment variables or a `.env` file.

Never hard-code passwords.

Example configuration:

DB_HOST=
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=

Also support:

CSV_PATH=
IMAGES_PATH=

if useful.

Provide a `.env.example`.

## DATABASE SAFETY

This is the most important requirement.

The importer must have:

1. `--dry-run`
2. normal import mode
3. a clear confirmation before writing
4. transaction handling per product
5. rollback on product failure
6. detailed logging
7. no deletion of unrelated records

Default behavior should be safe.

Ideally:

python importer.py products.csv --dry-run

does NOT modify anything.

Normal import should require an explicit flag such as:

python importer.py products.csv --import

Do not make normal database writes the default.

## PRODUCT MATCHING

Products must be matched by SKU.

For each CSV row:

1. Find an existing VirtueMart product using SKU.
2. If it exists:
   - update it
   - do NOT create a duplicate.
3. If it does not exist:
   - create a new product.
4. Keep the operation idempotent.

Running the same CSV twice should not create duplicate products, custom fields, media records, etc.

Do not rely on CSV row order for identity.

## PRODUCT DATA

Implement:

- SKU
- product title/name
- description
- English data
- Greek data
- published state
- price
- sizes
- colours
- fabric/material

Use the exact product tables and language tables discovered during reverse engineering.

The site requires both English and Greek product records.

Use the exact language codes and structure discovered in the analysis.

Do not invent Joomla language IDs.

## PRICE

The reverse-engineering phase established that VirtueMart stores the product price as NET price and applies the existing VAT calculation rule.

The discovered product example:

NET = 77.82258
VAT = 24%
GROSS = 96.50

The importer must therefore store the NET/base price in the correct VirtueMart price field and use the existing VirtueMart tax rule/product_tax_id discovered during analysis.

Do NOT store the gross price as the base product price.

Do NOT create a new VAT rule.

Use the existing tax configuration.

Do not round the stored net price incorrectly.

Follow the precision used by the existing database.

## CUSTOM FIELDS

The importer must support these exact existing custom fields:

- ID 6 = Size
- ID 7 = Colour
- ID 10 = Fabric

The reverse engineering established that these are simple string custom fields stored as individual product_customfields rows.

Therefore:

For:

sizes = 35|36|37|38

create one Size custom-field relationship per value.

For:

colours = BLK|RED

create one Colour custom-field relationship per value.

For:

fabric = Leather

create the Fabric custom-field relationship.

Do NOT use:

- Generic Variant
- Multi Variant
- VP Color Texture
- VP Fabric/Colour
- VP Size/Heel
- other advanced/plugin custom fields

unless the existing database analysis proves they are required for these imported products.

The importer must preserve the exact `customfield_params` / configuration values used by the existing installation.

Do not invent new custom-field definitions.

## CUSTOM FIELD PRICES

This requires special care.

The reverse-engineering phase found that `customfield_price` behaves as a NET SURCHARGE, not as an absolute product price.

It also found that existing Colour rows have price = 0.

The developer previously stated that Colour values may need a price equal to "product price minus VAT", but this was NOT supported by the database evidence.

Therefore:

DO NOT implement the developer's claimed Colour pricing behavior unless the database analysis now provides definitive evidence for it.

For Colour custom fields, reproduce the existing database convention.

If the correct value is zero, use zero.

Do not guess.

## PUBLISHED STATE

New products must be inserted with:

published = 0

Existing products being updated should preserve their existing published state unless there is an explicit importer option to change it.

Do not accidentally publish products during import.

## IMAGES

Implement image importing according to the exact media architecture discovered during reverse engineering.

Images are physically stored under the VirtueMart product media directory discovered in the analysis.

The importer should:

1. Match local images to SKU.
2. Determine deterministic image ordering.
3. Copy the image file to the correct VirtueMart media directory.
4. Register the image in the correct media table.
5. Create the product-media relationship.
6. Preserve ordering.
7. Make the first image the primary/main image according to the existing database convention.
8. Avoid duplicate media records/files when the importer is run again.

Do NOT store image binary data in the database if the existing installation only stores filesystem references.

Use the exact relative `file_url` convention discovered in the database.

Handle:

- spaces in filenames
- Unicode filenames
- `.jpg`, `.jpeg`, `.png`, and `.webp` if appropriate
- duplicate filenames
- missing images

If a product has no matching image, report it clearly but do not crash the entire import.

## CATEGORIES

Do NOT invent category behavior.

If the existing importer requirements do not provide a category column, preserve the existing/default category strategy determined from the database analysis.

If category assignment is necessary for newly created products, implement it as an explicit configurable option rather than silently guessing.

For example:

--category-id 62

If no category is supplied, do not randomly assign one.

## VALIDATION

Before modifying the database, validate the entire CSV.

Detect and report:

- duplicate SKUs
- missing SKU
- missing English title
- missing Greek title
- invalid price
- malformed sizes
- malformed colours
- missing image
- invalid image
- unknown fields
- empty required values

Provide a validation-only mode if useful.

The importer should preferably report all validation errors before starting database writes.

## DRY RUN

Dry-run output should be useful.

For each product show something similar to:

SKU: CD004
Operation: CREATE / UPDATE
EN title: ...
EL title: ...
Net price: ...
Sizes: 35,36,37,38
Colours: BLK
Fabric: ...
Images: 3
Published: 0

And show which database records would be inserted/updated.

Do not print database passwords.

## TRANSACTIONS

Use a transaction per product.

Conceptually:

BEGIN

find/create product
update language data
update price
update Size custom fields
update Colour custom fields
update Fabric custom fields
register/copy images
create media relationships
set published state

COMMIT

If anything fails:

ROLLBACK

Then continue with the next product and report the failure.

Do not leave partially imported products.

## EXISTING PRODUCT UPDATE BEHAVIOR

For existing SKUs, the importer should update the fields it owns.

It must NOT blindly delete every custom field belonging to the product.

Only manage:

- Size ID 6
- Colour ID 7
- Fabric ID 10
- price
- English/Greek product data
- images owned by this import operation if necessary

Preserve unrelated VirtueMart data/custom fields.

Before deciding how to replace existing Size/Colour/Fabric values, use the exact database structure from your analysis and make the operation deterministic and idempotent.

## LOGGING

Create a useful import report.

At minimum:

- total rows
- created
- updated
- skipped
- failed
- missing images
- validation errors
- database errors

Also write a timestamped log file.

Example:

logs/import-2026-09-07-183000.log

At the end print a summary.

## CLI

Provide a clean CLI.

Something along the lines of:

python importer.py products.csv --dry-run

python importer.py products.csv --import

python importer.py products.csv --import --limit 10

python importer.py products.csv --import --sku CD004

Useful options may include:

--dry-run
--import
--limit
--sku
--verbose
--category-id
--images
--db-host
etc.

Do not over-engineer the CLI unnecessarily.

## TESTING

Create tests for the important logic.

At minimum test:

- CSV parsing
- multi-value parsing
- SKU/image matching
- duplicate SKU detection
- price handling
- idempotency logic
- dry-run behavior

Where possible, test database logic against a local test database or controlled copy rather than production.

Do NOT require production credentials to run unit tests.

## IMPORTANT: USE CD004 AS THE REFERENCE

The existing product:

SKU = CD004
product ID = 494

was completely traced during the previous investigation.

Use it as the canonical reference when implementing.

The importer should produce database structures consistent with CD004 wherever applicable.

After implementation, perform a read-only comparison between the structures generated by the importer and the known CD004 structure.

Do NOT modify CD004 during testing unless explicitly using a safe local database copy.

## DO NOT DO THESE THINGS

Do NOT:

- create a Joomla extension
- create a VirtueMart plugin
- use browser automation
- use the old CSV importer
- scrape the website
- modify the SQL dump
- modify production during development/testing
- invent table structures
- invent language IDs
- invent custom field behavior
- create new VAT rules
- touch the advanced custom-field plugin system unnecessarily
- delete unrelated product data
- publish imported products by default

## DELIVERABLE

Implement the complete importer in the current project.

Also create:

- README.md
- .env.example
- requirements.txt or pyproject.toml
- appropriate tests
- example CSV
- logs directory handling
- clear source-code comments where VirtueMart-specific behavior is non-obvious

README must explain:

1. installation
2. configuration
3. CSV format
4. image naming convention
5. dry-run usage
6. import usage
7. how existing products are updated
8. how new products are created
9. how images are handled
10. how rollback works
11. how to test safely
12. important VirtueMart-specific assumptions

## FINAL VERIFICATION

After implementing:

1. Run formatting/linting if configured.
2. Run all tests.
3. Run the importer in dry-run mode against the example CSV.
4. Verify that no production database was modified.
5. Review the generated SQL/database operations for correctness.
6. Check idempotency carefully.
7. Report any remaining UNKNOWN items that require confirmation from the Joomla developer.

Do not stop after creating a skeleton.

Build the actual working importer.