-- For users --

This tool takes a purchase order pdf and returns a csv. When imported, this csv 
directly adds corresponding product catalogues to a shopify store.

This dramatically speeds up the time for updating a website. Instead of manually
searching for images and adding products one by one, just upload the pdf and import
with the outputted csv.

TODO
Here is a demo GIF showing the entire workflow. 

TODO
Here are the input and output for the above video

TODO
Dependencies for the tool are defined in the pyproject.toml
The project requires search engine scraper credentials (we use SerpAPI), an
openAI api key, proxy credentials (if no proxy desired set PROXY=None in webscrape.py),
and Shopify credentials. 
To link to shopify, the store admin must make and install a custom app in the 
developer dashboard. The app must have read and write permissions for 'products', 
'shopify admin', and 'online store'.
Shopify credentials include the store name and an app's client_id and secret.
The store name can be found in the Shopify store's settings and the app's
client_id and secret can be found in the app's settings in the dev dashboard.

To run the program as a CLI, just clone the repo and call tool/main.py {pdf_path} 
The -o is optional and lets you specify the output path of the resulting csv. You
can also use --output

To run the demo app as a locally hosted program, ensure you have uvicorn installed 
on your environent. To host the app locally, run 
    python -m uvicorn demo_app.app:app --reload 
This defaults to 127.0.0.0:8000, and the port can be modified by additionally
passing in --port {port_number}. Accessing  http://127.0.0.1:{port_number} on
any browser should bring up the web app wrapper for the program.

-- For people curious about how it works --


This is the program's flow and describes what goes on behind the scenes 
1. Input a purchase order pdf
2. Extract an 'OrderTable' from the pdf which includes the vendors and 
   product_codes for each line item
3. Google each product and scrape the first link for images and metadata. 
    Add this info to the ordertable
4. Have AI "select" which of the images are of the product
5. Download the selected images locally
6. Upload the images from local to shopify. 
7. Get public urls for each image and add them to the table
8. From the fully populated order table, structure the csv


Project Structure
tool/
  main.py                   CLI entrypoint
  pipeline.py               End-to-end PDF-to-Shopify-CSV workflow
  pdf_extraction.py         Extracts order data from PDFs
  enrichment.py             Orchestrates search, scraping, image selection, and
                            downloads for adding images to the table.
  web_scrape.py             Searches product pages, scrapes candidate image data,
                            and generates inputs to image selection
  image_selection.py        Uses OpenAI to select likely product images
  local_download.py         Downloads selected images to local files
  shopify_upload_files.py   Uploads local images to Shopify Files
  shopify_formatting.py     Formats enriched orders into Shopify import CSV rows
  types.py                  Shared TypedDict definitions
  debug_view.py             Generates visual debugging output

demo_app/
  app.py                    FastAPI demo server
  index.html                Browser UI for uploading PDFs and downloading CSVs
  my_script.py              Adapter between the demo app and the pipeline

Data flow

The product is currently structured as OrderTables.
An Order represents a single product or line item from a purchase order.
An OrderTable is a collection of Orders.
These get enriched by having Images added to every order.
They become robust when every Image in them are robust.

A CandidateImage is an image that has been scraped from the product page
but not yet selected as an image of the product to be uploaded. It contains useful
metadata which the AI considers when selecting images. 
A WeakImage is the datatype used to store selected images and useful data about
the image, such as the confidence score and the local path it was downloaded to.
A RobustImage is an image that has sufficient non-null fields to be used when
constructing the csv. Local download errors or shopify upload errors can prevent
an image from becoming robust. 

The results of an initial product page scrape is structured as a 
ProductPageData object. AI leverages this to generate product catalogue information,
such as the best images of the product, in the form of a ProductPageAnalysis.

There are also many types describing Shopify API's desired inputs and results.
For more information check their documentation.

Tech Stack
- Python
- FastAPI for the demo web app
- pdfplumber for PDF table extraction
- OpenAI API for data normalization and image selection
- BeautifulSoup / Playwright for product page web scraping
- Shopify's graphql Admin API for image uploads

Current Scope
Some pdf structures are known to be difficult to extract data from. The types
of pdf structures this works with has not been tested.

Some vendors are known to have websites with robust anti-bot measures and these can
be difficult to scrape. The vendores the tool works for has not been tested.

The WebUI can be improved with a manual review screen. Confidence scores for
each image can be added to facilitate this. The UI can also be improved
by allowing multiple pdfs to be uploaded at once.

Many shops can not use model's likenesses, and need to crop the faces out of
images containing them. This can be added as a feature to make the tool even
more useful.

The pipeline can be sped up with parallelism (when scraping
and uploading to shopify).

The Shopify token generation flow can be automated to not require a new token
to be produced before each use. 