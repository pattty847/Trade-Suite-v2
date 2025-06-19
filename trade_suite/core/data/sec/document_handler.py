import os
import logging
import re
import json
import asyncio
from typing import List, Dict, Optional, Callable, Awaitable

# Assuming http_client defines SecHttpClient with make_request method
from .http_client import SecHttpClient

class FilingDocumentHandler:
    """Handles fetching specific documents and document lists from SEC filings."""

    BASE_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data"

    def __init__(self, http_client: SecHttpClient, cik_lookup_func: Callable[[str], Awaitable[Optional[str]]]):
        """
        Initialize the FilingDocumentHandler.

        Args:
            http_client (SecHttpClient): An instance of the HTTP client for making requests.
            cik_lookup_func (Callable[[str], Awaitable[Optional[str]]]): An awaitable function
                                                                      (like SECDataFetcher.get_cik_for_ticker)
                                                                      to resolve tickers to CIKs.
        """
        self.http_client = http_client
        self.get_cik_for_ticker = cik_lookup_func # Function to get CIK from ticker

    async def _get_cik_for_filing(self, accession_no: str, ticker: Optional[str] = None) -> Optional[str]:
        """
        Determines the CIK to use in the URL path for a specific filing's archive.

        It first attempts to get the CIK using the provided `ticker` via the `cik_lookup_func`,
        as this is generally more reliable. If the ticker is not provided or the lookup fails,
        it falls back to extracting the first 10 digits from the `accession_no` if they are numeric.
        The CIK is returned without leading zeros, as required for the SEC archive URL structure.

        Args:
            accession_no (str): The filing accession number (dashes optional).
            ticker (Optional[str], optional): The stock ticker symbol associated with the filing,
                used as a primary hint for CIK lookup. Defaults to None.

        Returns:
            Optional[str]: The CIK string suitable for the URL path (no leading zeros),
                or None if a CIK could not be reliably determined.
        """
        cik_for_url = None
        accession_no_clean = accession_no.replace('-', '')

        # 1. Try CIK from ticker (most reliable)
        if ticker:
            try:
                cik_lookup = await self.get_cik_for_ticker(ticker)
                if cik_lookup:
                    cik_for_url = cik_lookup.lstrip('0')
                    logging.debug(f"Using CIK {cik_for_url} from ticker {ticker} for filing {accession_no}.")
            except Exception as e:
                logging.warning(f"Error looking up CIK for ticker {ticker} for filing {accession_no}: {e}")

        # 2. Fallback: Try to extract CIK-like part from accession number
        if not cik_for_url:
            # Accession number format: 0001193125-23-017489 -> CIK part is 0001193125
            cik_part_from_acc = accession_no_clean[:10]
            if cik_part_from_acc.isdigit():
                cik_for_url = cik_part_from_acc.lstrip('0')
                logging.debug(f"Using CIK {cik_for_url} extracted from accession {accession_no}.")
            else:
                logging.warning(f"Could not extract valid CIK part from accession number: {accession_no}")

        if not cik_for_url:
            logging.error(f"Could not determine CIK for URL construction for filing {accession_no} (ticker: {ticker}).")
            return None

        return cik_for_url

    def _get_sec_archive_headers(self) -> Dict[str, str]:
        """
        Generates the necessary HTTP headers for requests to `www.sec.gov/Archives`.

        It takes the default headers from the injected `SecHttpClient` (which includes the
        essential User-Agent) and specifically overrides the `Host` header to `www.sec.gov`,
        as required for accessing the archive endpoints.

        Returns:
            Dict[str, str]: A dictionary of HTTP headers.
        """
        # Create headers based on http_client's default, but override Host
        headers = self.http_client.default_headers.copy()
        headers['Host'] = 'www.sec.gov'
        return headers

    async def get_filing_documents_list(self, accession_no: str, ticker: Optional[str] = None) -> Optional[List[Dict]]:
        """
        Fetches the list of documents contained within a specific SEC filing.

        It primarily attempts to retrieve and parse the `index.json` file associated
        with the filing's archive directory. This JSON file usually lists all documents
        with their names, types, and sizes.

        Args:
            accession_no (str): The SEC filing accession number (e.g., '0000320193-23-000106').
                Dashes are optional.
            ticker (str, optional): The stock ticker symbol, used as a hint for CIK lookup
                to construct the correct archive URL. Defaults to None.

        Returns:
            Optional[List[Dict]]: A list of dictionaries, where each dictionary represents
                a document found in the filing's index. Keys typically include 'name',
                'type', 'size', and 'last_modified'. Returns None if the index cannot be
                fetched, parsed, or if an error occurs.
        """
        accession_no_clean = accession_no.replace('-', '')
        cik_for_url = await self._get_cik_for_filing(accession_no, ticker)
        if not cik_for_url:
            return None

        index_json_url = f"{self.BASE_ARCHIVE_URL}/{cik_for_url}/{accession_no_clean}/index.json"
        logging.info(f"Fetching document list via index.json: {index_json_url}")

        try:
            headers = self._get_sec_archive_headers()
            index_data = await self.http_client.make_request(index_json_url, headers=headers, is_json=True)

            if not isinstance(index_data, dict) or 'directory' not in index_data:
                logging.warning(f"index.json for {accession_no} did not return expected structure. Type: {type(index_data)}. Attempting index.htm next.")
                # TODO: Optionally fallback to parsing index.htm here if index.json fails
                return None # For now, return None if JSON fails

            documents = []
            for item in index_data.get('directory', {}).get('item', []):
                doc_info = {
                    'name': item.get('name'),
                    'type': item.get('type'),
                    'size': item.get('size'),
                    'last_modified': item.get('last_modified')
                }
                if doc_info['name']:
                    documents.append(doc_info)

            logging.info(f"Found {len(documents)} documents in index.json for {accession_no}")
            return documents

        except Exception as e:
            logging.error(f"Error fetching/parsing index.json for document list ({accession_no}): {e}", exc_info=True)
            return None

    async def download_form_document(self, accession_number: str, document_name: str, ticker: Optional[str] = None) -> Optional[str]:
        """
        Downloads the raw content of a specific document file from a filing's archive.

        This method requires knowing the exact `document_name` (e.g., 'form4.xml',
        'aapl-20230930.htm') within the specified `accession_number`'s filing directory.
        Use `get_filing_documents_list` first if the document name is unknown.

        Args:
            accession_number (str): The SEC filing accession number (dashes optional).
            document_name (str): The exact filename of the document to download from the filing.
            ticker (str, optional): The stock ticker symbol, used as a hint for CIK lookup
                to construct the correct download URL. Defaults to None.

        Returns:
            Optional[str]: The raw textual content of the document (e.g., HTML, XML, plain text)
                as a string, or None if the document cannot be found, the download fails,
                or an error occurs.
        """
        if not accession_number or not document_name:
             logging.error("Accession number and document name are required.")
             return None

        accession_no_clean = accession_number.replace('-', '')
        cik_for_url = await self._get_cik_for_filing(accession_number, ticker)
        if not cik_for_url:
            return None

        # Construct the URL
        url = f"{self.BASE_ARCHIVE_URL}/{cik_for_url}/{accession_no_clean}/{document_name}"
        logging.info(f"Attempting to download document from: {url}")

        try:
            headers = self._get_sec_archive_headers()
            logging.debug(f"Using headers for document download: {headers}")

            # Fetch as raw text (is_json=False)
            response_content = await self.http_client.make_request(url, headers=headers, is_json=False)

            if response_content is None:
                # Error logged within make_request
                logging.error(f"Failed to download document {document_name} ({accession_number}) from {url}. Check logs for details.")
                return None

            # Content type check is unreliable, return the text
            return response_content

        except Exception as e:
            # Catch unexpected errors during the download process itself
            logging.error(f"Unexpected error downloading document {document_name} ({accession_number}) from {url}: {e}", exc_info=True)
            return None

    async def _find_primary_document_name(self, accession_no: str, cik_for_url: str) -> Optional[str]:
        """
        Attempts to automatically determine the name of the main document within a filing.

        This is a heuristic process used when the specific document name isn't provided.
        It prioritizes finding common patterns or types associated with primary documents.

        Strategy:
        1. Fetch and parse `index.json`: Looks for files ending in .htm, .html, or .xml.
           Prioritizes files containing form identifiers (like 'form4', '10k') or specific
           types ('XML', '10-K').
        2. Fallback to fetching and parsing `index.htm`: If `index.json` fails or yields no
           candidates, it scans the HTML index page for common link patterns (e.g.,
           'form4.xml', 'd\d+k.htm', 'primary_doc.htm') or the first .htm/.xml link
           within the main filing table.

        Args:
            accession_no (str): The filing accession number (dashes cleaned).
            cik_for_url (str): The CIK part (no leading zeros) for the archive URL.

        Returns:
            Optional[str]: The determined filename of the likely primary document, or None
                if no suitable candidate could be identified.
        """
        accession_no_clean = accession_no.replace('-', '')
        headers = self._get_sec_archive_headers()
        primary_doc = None

        # 1. Try index.json
        index_json_url = f"{self.BASE_ARCHIVE_URL}/{cik_for_url}/{accession_no_clean}/index.json"
        logging.debug(f"Looking for primary document via index.json: {index_json_url}")
        try:
            index_data = await self.http_client.make_request(index_json_url, headers=headers, is_json=True)
            if isinstance(index_data, dict) and 'directory' in index_data:
                potential_docs = []
                for item in index_data.get('directory', {}).get('item', []):
                    name = item.get('name', '')
                    doc_type = item.get('type', '')  # e.g., '10-K', 'XML', 'GRAPHIC'
                    if name.lower().endswith(('.xml', '.htm', '.html')) and not name.lower().endswith('-index.html'):
                        # Prioritize based on common patterns or type
                        if 'form4' in name.lower() or 'f345' in name.lower() or (doc_type and 'XML' in doc_type.upper()):
                            potential_docs.insert(0, name)  # High priority
                        elif any(ft in name.lower() for ft in ['10k', '10q', '8k']) or (
                            doc_type and any(ft in doc_type for ft in ['10-K', '10-Q', '8-K'])
                        ):
                            potential_docs.insert(0, name)  # Medium priority
                        else:
                            potential_docs.append(name)  # Lower priority
                if potential_docs:
                    primary_doc = potential_docs[0]
                    logging.info(f"Found primary document candidate from index.json: {primary_doc}")
            else:
                logging.warning(f"index.json for {accession_no} didn't return expected directory structure.")
        except Exception as e:
            logging.error(f"Error parsing index.json for {accession_no}: {e}")

        # 2. Fallback to index.htm if no candidate from index.json
        if not primary_doc:
            index_html_url = f"{self.BASE_ARCHIVE_URL}/{cik_for_url}/{accession_no_clean}/index.htm"
            logging.debug(f"Falling back to HTML index page: {index_html_url}")
            try:
                index_html = await self.http_client.make_request(index_html_url, headers=headers, is_json=False)
                if index_html and isinstance(index_html, str):  # Check if we got valid HTML
                    # Simple regex patterns for common primary docs - capturing filename part
                    patterns = [
                        r'''href=["'][^"']*(form4\.xml)["']''',           # Form 4 XML
                        r'''href=["'][^"']*(d\d+k\.htm)["']''',          # 8-K patterns like d123456k.htm
                        r'''href=["'][^"']*(dq\.htm)["']''',             # 10-Q patterns like dq.htm
                        r'''href=["'][^"']*(\w+-\d{8}\.htm)["']''',   # Common pattern like msft-20230630.htm
                        r'''href=["'][^"']*(10-?[kq]\.htm)["']''',        # 10-K / 10-Q htm
                        r'''href=["'][^"']*(primary_doc\.xml)["']''',    # Explicit primary_doc.xml
                        r'''href=["'][^"']*(primary_doc\.htm)["']'''     # Explicit primary_doc.htm
                    ]
                    found_match = None
                    for pattern in patterns:
                        match = re.search(pattern, index_html, re.IGNORECASE)
                        if match:
                            found_match = match.group(1)  # Capture the filename part
                            break

                    if found_match:
                        primary_doc = found_match
                        logging.info(f"Found primary document candidate from index.htm: {primary_doc}")
                    else:
                        # Last resort: find first .htm or .xml link in the main table
                        table_match = re.search(r'''<table.*?>(.*?)</table>''', index_html, re.DOTALL | re.IGNORECASE)
                        if table_match:
                            table_html = table_match.group(1)
                            link_match = re.search(r'''href=["']([^"']+\.(?:htm|xml))["']''', table_html, re.IGNORECASE)
                            if link_match:
                                # Extract filename from potential path
                                primary_doc = os.path.basename(link_match.group(1))
                                logging.info(f"Found potential primary document via first link in index.htm table: {primary_doc}")
            except Exception as e:
                logging.error(f"Error processing HTML index for {accession_no}: {e}")

        if not primary_doc:
            logging.error(f"Could not determine primary document for {accession_no}")
            return None

        return primary_doc

    async def fetch_filing_document(self, accession_no: str, primary_doc: Optional[str] = None, ticker: Optional[str] = None) -> Optional[str]:
        """
        Fetches the content of the primary document for a given SEC filing.

        This acts as a higher-level convenience method. If `primary_doc` filename is
        provided, it directly calls `download_form_document`. If `primary_doc` is None,
        it first calls `_find_primary_document_name` to attempt auto-detection and then
        downloads the identified document.

        Args:
            accession_no (str): The SEC filing accession number (e.g., '0001193125-23-017489').
                Dashes are optional.
            primary_doc (str, optional): The specific filename of the document within the filing
                (e.g., 'd451917d8k.htm'). If None, the method attempts to automatically
                determine the primary document name. Defaults to None.
            ticker (str, optional): The stock ticker symbol. Used as a hint to find the CIK
                more reliably, especially important for auto-detection. Defaults to None.

        Returns:
            Optional[str]: The textual content (HTML, XML, or plain text) of the specified or
                auto-determined primary document, or None if an error occurs, the document
                cannot be identified, or download fails.
        """
        cik_for_url = await self._get_cik_for_filing(accession_no, ticker)
        if not cik_for_url:
            return None

        document_to_fetch = primary_doc
        if not document_to_fetch:
            logging.info(f"Primary document not specified for {accession_no}. Attempting auto-detection.")
            document_to_fetch = await self._find_primary_document_name(accession_no, cik_for_url)

        if not document_to_fetch:
            logging.error(f"Could not find or determine primary document for {accession_no}. Cannot fetch content.")
            return None

        # Now download the determined/specified document
        logging.info(f"Fetching document '{document_to_fetch}' for filing {accession_no}")
        return await self.download_form_document(accession_no, document_to_fetch, ticker) # Reuse download method


    async def download_form_xml(self, accession_no: str, ticker: Optional[str] = None) -> Optional[str]:
        """
        Downloads the primary XML document (typically for Form 4/insider filings) for a given filing.

        This method specifically targets XML files commonly used for machine-readable
        data in certain filing types (most notably Form 4).

        Strategy:
        1. Fetch the document list using `get_filing_documents_list` (via `index.json`).
        2. Search the list for filenames matching common XML patterns (e.g., `form4.xml`,
           `f345.xml`, `primary_doc.xml`, `*.xml`). It prioritizes known Form 4 patterns.
        3. If a suitable XML document is found, download it using `download_form_document`.

        Args:
            accession_no (str): The SEC filing accession number (dashes optional).
            ticker (str, optional): The stock ticker symbol of the *issuer*. Used as a hint
                for CIK lookup needed to fetch the document list and download the file.
                Defaults to None.

        Returns:
            Optional[str]: The content of the identified XML file as a string, or None if no
                suitable XML document is found in the index, or if download/parsing fails.
        """
        cik_for_url = await self._get_cik_for_filing(accession_no, ticker)
        if not cik_for_url:
            return None

        # Find XML file name first from index.json (preferable)
        xml_file_name = None
        documents = await self.get_filing_documents_list(accession_no, ticker)
        if documents:
            # Look for likely XML candidates
            xml_candidates = []
            for doc in documents:
                name = doc.get('name', '')
                doc_type = doc.get('type', '')
                if name.lower().endswith('.xml'):
                    if 'form4' in name.lower() or 'f345' in name.lower() or (doc_type and 'XML' in doc_type.upper()):
                         xml_candidates.insert(0, name) # High priority
                    else:
                         xml_candidates.append(name)
            if xml_candidates:
                 xml_file_name = xml_candidates[0]
                 logging.info(f"Found XML document candidate via index.json: {xml_file_name}")

        if not xml_file_name:
            # Fallback: maybe try finding primary doc and check if it's XML?
            # This is less reliable as primary might be HTML
            logging.warning(f"Could not find specific XML file in index.json for {accession_no}. Will attempt download based on generic name if needed by caller.")
            # Or just return None if strict XML is required
            return None

        # Download the found XML file
        logging.info(f"Downloading XML file '{xml_file_name}' for filing {accession_no}")
        return await self.download_form_document(accession_no, xml_file_name, ticker)


    async def download_all_form_documents(self, accession_no: str, ticker: Optional[str] = None, output_dir: Optional[str] = None) -> Dict[str, Optional[str]]:
        """
        Downloads all documents listed in a filing's index and optionally saves them.

        Fetches the document list using `get_filing_documents_list`. Then, concurrently
        downloads each document using `download_form_document` via `asyncio.gather`.
        If `output_dir` is specified, each downloaded document's content is saved to a
        file within that directory.

        Note: This can be resource-intensive for filings with many large documents.

        Args:
            accession_no (str): The SEC filing accession number (dashes optional).
            ticker (str, optional): The stock ticker symbol hint for CIK lookup. Defaults to None.
            output_dir (str, optional): If provided, the directory where downloaded documents
                will be saved. The directory will be created if it doesn't exist.
                If None, documents are downloaded but only returned in the result dictionary.
                Defaults to None.

        Returns:
            Dict[str, Optional[str]]: A dictionary where keys are the filenames of the documents
                listed in the index, and values are their downloaded content as strings.
                If a specific document download fails, its value will be None.
                Returns an empty dictionary if the initial document list cannot be fetched.
        """
        document_list = await self.get_filing_documents_list(accession_no, ticker)
        if not document_list:
            logging.error(f"Cannot download all documents for {accession_no}, failed to get document list.")
            return {}

        if output_dir:
            # Ensure output directory exists
            target_dir = os.path.join(output_dir, accession_no.replace('-',''))
            os.makedirs(target_dir, exist_ok=True)
            logging.info(f"Will save downloaded files to: {target_dir}")

        async def download_and_save(doc_info): # Helper coroutine
            doc_name = doc_info.get('name')
            if not doc_name:
                return doc_name, None # Skip if name is missing

            content = await self.download_form_document(accession_no, doc_name, ticker)

            if content is not None and output_dir and target_dir:
                file_path = os.path.join(target_dir, doc_name)
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logging.debug(f"Saved document {doc_name} to {file_path}")
                except Exception as e:
                    logging.error(f"Error saving document {doc_name} to {file_path}: {e}")
                    # Content is still returned even if saving fails
            elif content is None:
                 logging.warning(f"Failed to download document: {doc_name}")

            return doc_name, content

        # Create download tasks
        tasks = [download_and_save(doc) for doc in document_list if doc.get('name')] # Ensure name exists

        # Run tasks concurrently
        logging.info(f"Starting concurrent download of {len(tasks)} documents for {accession_no}...")
        results = await asyncio.gather(*tasks)
        logging.info(f"Finished downloading documents for {accession_no}.")

        # Convert list of tuples [(name, content), ...] to dict {name: content, ...}
        downloaded_docs = {name: content for name, content in results if name}
        return downloaded_docs 