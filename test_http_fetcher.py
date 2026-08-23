import asyncio

from ingestion.http_fetcher import HTTPFetcher
from processors.html_processor import HTMLProcessor


async def main():

    url = "https://www.rapidresponseuc.com/"

    print("\n========================================")
    print("       FULL HTTP → HTML TEST")
    print("========================================\n")

    # -------------------------------------
    # STEP 1: Fetch the website
    # -------------------------------------

    print(f"Fetching: {url}")

    fetcher = HTTPFetcher()

    html = await fetcher.fetch(url)

    print(f"✓ HTML received: {len(html)} characters")

    # -------------------------------------
    # STEP 2: Process the HTML
    # -------------------------------------

    processor = HTMLProcessor()

    result = processor.process(html)

    # -------------------------------------
    # STEP 3: Display results
    # -------------------------------------

    print("\n---------- RESULTS ----------\n")

    print("TEXT LENGTH:")
    print(len(result["text"]))

    print("\nTEXT PREVIEW:")
    print(result["text"][:500])

    print("\nEMAILS:")
    print(result["emails"])

    print("\nPHONES:")
    print(result["phones"])

    print("\n========================================")
    print("              TEST COMPLETE")
    print("========================================\n")


asyncio.run(main())