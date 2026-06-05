""" Types used throughout the tool. Seperated by initial flow and then
Shopify specific

Core flow:
- Order: one extracted purchase-order line item.
- OrderTable: a collection of extracted orders.
- CandidateImage: An image scraped from a product page that AI has NOT confirmed is of a product.
- WeakImage: a image that IS of the product but may still be missing local path or Shopify data.
- RobustImage: An image that has no non-null fields and ready to be formatted for the csv
- EnrichedOrder: an order plus title, source URL, selected images, warnings, and debug data.
- RobustOrder: an enriched order whose images have required local and public URLs.

"""

from typing import List, Optional, TypedDict, Required, NotRequired, TypeAlias
from pathlib import Path

class CandidateImage(TypedDict):
    candidate_index: int
    page_url: str # url of site image scraped from
    src_url: str # url that got scraped of the image
    alt_text: str | None
    # confidence ?

class WeakImage(CandidateImage):
    local_path: Path | None
    public_url: str | None
    confidence: float
    of_a_model: bool | None
    cropped: bool | None
    errors: List[str]

class RobustImage(CandidateImage):
    local_path: Path
    public_url: str
    confidence: float
    of_a_model: bool
    cropped: bool
    errors: List[str]

class ProductPageData(TypedDict):
    main_url: str
    html: str
    image_urls: List[str]
    alt_texts: List[str | None]
    warnings: List[str]
    used_playwright: bool # debugging

class ProductPageAnalysis(TypedDict):
    candidate_images: List[CandidateImage]
    product_title: Optional[str]
    selected_image_indices: List[int] | None
    error: str | None
    summary: str | None
    raw_AI_output: str | None

class Order(TypedDict):
    vendor: str
    product_code: str | None
    quantity: int | None

class OrderDebugDict(TypedDict):
    page_data: ProductPageData # contains html and used_playwright
    page_analysis: ProductPageAnalysis # contains candidate_images and summary and raw output

class EnrichedOrder(Order):
    images: List[WeakImage] # These are selected_images
    title: str
    warnings: List[str]
    main_url: str  # url associated with the order and where images scraped from
    debug: OrderDebugDict | None

class OrderTable(TypedDict, total=False):
    orders: List[Order]

class EnrichedOrderTable(TypedDict, total=False):
    orders: List[EnrichedOrder]

class RobustOrder(Order):
    images: List[RobustImage]
    title: str
    warnings: List[str]
    main_url: str # url associated with the order and where images scraped from
    debug: OrderDebugDict | None

class RobustOrderTable(TypedDict, total=False):
    orders: List[RobustOrder]

# -------- Shopify file uploading related types --------
class UserError:
    field: List[str]
    message: str

class ShopifyParameter(TypedDict):
    name: str
    value: str

class StagedTarget(TypedDict):
    resourceUrl: str
    url: str
    parameters: List[ShopifyParameter]

class StagedUploadsCreate(TypedDict):
    stagedTargets: List[StagedTarget]
    userErrors: List[UserError]

class StagedUploadsCreateData(TypedDict):
    stagedUploadsCreate: StagedUploadsCreate

class StagedUploadsCreateInput(TypedDict):
    filename: str
    mimeType: str
    resource: str
    httpMethod: str

class StagedUploadsVariables(TypedDict):
    input : List[StagedUploadsCreateInput]

class FileCreateInput(TypedDict):
    originalSource: str
    alt: str
    contentType: str

class FileCreateVariables(TypedDict):
    files: List[FileCreateInput]

class FileCreateFile(TypedDict):
    id: str
    fileStatus: str
    alt: str

class FileCreate(TypedDict):
    files: List[FileCreateFile]
    userErrors: List[UserError]

class FileCreateData(TypedDict):
    fileCreate: FileCreate

class ShopifyImage(TypedDict):
    url: str

class FilePreview(TypedDict):
    image: ShopifyImage

class CheckFileStatusNode(TypedDict):
    fileStatus: str
    preview: FilePreview

class CheckFileStatusData(TypedDict):
    node: CheckFileStatusNode

class CheckFileStatusVariables(TypedDict):
    id : str

MyShopifyVariables: TypeAlias = StagedUploadsVariables | FileCreateVariables | CheckFileStatusVariables
MyShopifyResponse: TypeAlias = StagedUploadsCreateData | FileCreateData | CheckFileStatusData

# -------- Types for generating Shopify csv from enriched table --------

ShopifyFirstRow: TypeAlias = dict[str, str]
ShopifyNotFirstRow: TypeAlias = dict[str, str]
ShopifyCSVRow: TypeAlias = ShopifyFirstRow | ShopifyNotFirstRow