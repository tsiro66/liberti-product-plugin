"""Configuration loading.

Credentials and environment-specific paths come from environment variables or a
.env file in the project root. Nothing is hard-coded.

VirtueMart-specific constants below were established by the reverse-engineering
phase (see virtuemart-database-analysis.md) and must NOT be guessed:
  - table prefix xhngw_
  - vendor id 1, currency 47 (EUR), tax calc rule 1 (VAT 24%)
  - custom field ids 6=Size, 7=Colour, 10=Fabric
  - media path prefix images/stories/virtuemart/product/
  - default product_params / customfield_params strings (copied verbatim from CD004)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --- Values fixed by the database analysis (safe defaults, overridable) -----

#: Table prefix of the target installation.
TABLE_PREFIX = "xhngw_"

#: The single shop vendor (xhngw_virtuemart_vendors).
VENDOR_ID = 1

#: Currency 47 = EUR (xhngw_virtuemart_currencies).
CURRENCY_ID = 47

#: Global VAT calc rule id 1 = "VAT 24%" (xhngw_virtuemart_calcs), kind VatTax.
TAX_CALC_ID = 1

#: Custom field definition ids (xhngw_virtuemart_customs, field_type='S').
CUSTOM_SIZE = 6
CUSTOM_COLOUR = 7
CUSTOM_FABRIC = 10

#: Relative file_url prefix for product images (virtuemart_configs.media_product_path).
MEDIA_URL_PREFIX = "images/stories/virtuemart/product"

#: product_params default, copied verbatim from CD004 / all 431 products.
PRODUCT_PARAMS_DEFAULT = (
    'min_order_level=""|max_order_level=""|step_order_level=""|shared_stock=0|product_box=""'
)

#: customfield_params for customs 6/7/10, identical on all 10,670 existing rows.
CUSTOMFIELD_PARAMS = 'product_sku=""|product_gtin=""|product_mpn=""||'

DEFAULT_ENV_PATHS = (".env",)


@dataclass
class Config:
    # --- database ---------------------------------------------------------
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""
    #: "mysql" (PyMySQL/MariaDB) or "sqlite" (testing against a dump copy).
    db_backend: str = "mysql"

    # --- paths -------------------------------------------------------------
    csv_path: str = ""
    images_path: str = "images"
    #: Absolute server path of the VirtueMart product media directory.
    #: .env.example ships the value discovered in the analysis
    #: (/home/support/web/libertidance.com/public_html/images/stories/virtuemart/product).
    vm_media_dir: str = ""
    log_dir: str = "logs"

    # --- VirtueMart conventions ---------------------------------------------
    #: Joomla user id written to created_by/modified_by (shop uses 119 = "Liberti Dancewear").
    vm_admin_user_id: int = 0
    #: VAT percent, only used when price_mode == "gross" (rule 1 = 24%).
    vat_rate: float = 24.0
    #: "net" -> CSV price stored verbatim (DB convention); "gross" -> CSV price is
    #: the final VAT-inclusive shop price; stored net = price / (1 + vat/100).
    price_mode: str = "net"

    # --- importer behaviour -------------------------------------------------
    #: Applied to every imported product when set; default: create=0, update=keep.
    set_published: int | None = None
    #: Category assigned to NEW products (existing products keep theirs).
    category_id: int | None = None

    runtime_overrides: dict = field(default_factory=dict)

    @property
    def media_url_prefix(self) -> str:
        return MEDIA_URL_PREFIX


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config(env_file: str | None = None, cli_overrides: dict | None = None) -> Config:
    """Build a Config from OS env, optional .env file, then CLI overrides.

    Precedence: CLI > process environment > .env file > defaults.
    A tiny .env parser is used so that the package has no hard dependency on
    python-dotenv (it is still listed in requirements.txt for convenience).
    """
    env: dict[str, str] = {}

    candidates = [env_file] if env_file else list(DEFAULT_ENV_PATHS)
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                env.setdefault(key, value)
            break

    def get(key: str, default: str = "") -> str:
        return os.environ.get(key) or env.get(key) or default

    cfg = Config(
        db_host=get("DB_HOST", "127.0.0.1"),
        db_port=int(get("DB_PORT", "3306")),
        db_name=get("DB_NAME"),
        db_user=get("DB_USER"),
        db_password=get("DB_PASSWORD"),
        db_backend=get("DB_BACKEND", "mysql").lower(),
        csv_path=get("CSV_PATH"),
        images_path=get("IMAGES_PATH", "images"),
        vm_media_dir=get("VM_MEDIA_DIR"),
        log_dir=get("LOG_DIR", "logs"),
        vm_admin_user_id=int(get("VM_ADMIN_USER_ID", "0")),
        vat_rate=float(get("VM_VAT_RATE", "24")),
        price_mode=get("PRICE_MODE", "net").lower(),
    )
    if cfg.price_mode not in {"net", "gross"}:
        raise ValueError(
            f"PRICE_MODE must be 'net' or 'gross', got {cfg.price_mode!r}")

    for key, value in (cli_overrides or {}).items():
        if value is not None:
            setattr(cfg, key, value)
    return cfg
