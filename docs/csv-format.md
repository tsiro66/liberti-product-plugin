# Products CSV — how to structure your file

One row = one product. Save as **UTF-8** (Excel: "CSV UTF-8"). The first line
is the header and must contain the column names exactly as below — order
doesn't matter, but a misspelled column name is rejected.

```csv
sku,title_en,description_en,title_el,description_el,price,sizes,colours,fabric,short_desc_en,short_desc_el,category_id,manufacturer_id
```

Only `sku`, the two titles, the two descriptions and `price` are required.
Everything else can be left out or left empty.

## Columns

| Column | Required | What it does |
|---|---|---|
| `sku` | ✔ | Product code. Identity — must be unique. `102` and `102 ` (space) are treated as the same product. |
| `title_en` / `title_el` | ✔ | Product name in English / Greek. |
| `description_en` / `description_el` | ✔ | Long description. HTML allowed (`<p>...</p>`). Quote the cell if it contains commas. |
| `price` | ✔ | The **final customer price including 24% VAT**. Dot as decimal separator (`35.90`); one comma is tolerated (`35,90`). The importer stores the net equivalent automatically. |
| `sizes` | – | Sizes, separated by `\|` (pipe): `36\|37\|38`. Order in the cell = order in the shop. |
| `colours` | – | Colours, same pipe rule: `BLK\|NAVY`. |
| `fabric` | – | Fabric, same pipe rule: `Leather\|Suede`. |
| `short_desc_en` / `short_desc_el` | – | Short description (used for meta description). |
| `category_id` | – | Shop category id. Several = pipe-separated: `62\|65`. Leave **empty** for no category. |
| `manufacturer_id` | – | Shop manufacturer id. **One only** (never pipe-separated). Empty = none. |

## Rules that bite people

1. **Pipe = "several values".** Inside one cell: `36|37|38`. No spaces needed
   (spaces around values are trimmed).
2. **Empty cell meanings are deliberate:**
   - empty `sizes`/`colours`/`fabric` → existing values are left untouched
   - empty `category_id`/`manufacturer_id` → none set
3. **Ids must exist.** `category_id` and `manufacturer_id` are checked against
   the shop database; a wrong id stops that row with a clear error. Find ids
   with the queries in `README.md` or ask.
4. **Duplicate SKU in the file** = error. **SKU already in the shop** = the row
   is skipped (never updated).
5. **Prices are VAT-inclusive final prices.** Never pre-divide by 1.24.

## Worked example

```csv
sku,title_en,description_en,title_el,description_el,price,sizes,colours,fabric,short_desc_en,short_desc_el,category_id,manufacturer_id
DYO-101,Dance You Ballet Slipper,"<p>Soft ballet slipper with elastic drawstring.</p>",Ballet Slipper DYO-101,"<p>Απαλό μποτάκι μπαλέτου.</p>",35.90,36|37|38|39|40,09 Black|BLK,Leather,Soft ballet slipper,Απαλό μποτάκι,61,
DYO-205,Dance You Latin Shoe,"<p>Latin shoe with suede sole.</p>",Latin Shoe DYO-205,"<p>Παπούτσι λάτιν.</p>",52.00,35|36|37|38,09 Black|TAN,Suede,Latin dance shoe,Παπούτσι λάτιν,62|65,17
DYO-310,Headband,"<p>Plain headband.</p>",Headband DYO-310,"<p>Απλή ταινία κεφαλιού.</p>",6.90,,,,Accessories headband,Ταινία κεφαλιού,25,
```

- Row 1: pointe/ballet shoe → Ballet (61), no manufacturer yet.
- Row 2: two categories (Latin + Ballroom Various), manufacturer 17.
- Row 3: accessory — no sizes, colours or fabric at all.

## Before you send a file to the importer

1. Open it in a text editor (not just Excel) and check the header line.
2. Run the dry-run cron first — **always**. Read `dryrun-out.txt` line by line.
3. Only then the import. New products arrive **unpublished**; publish them in
   the shop admin after checking.
