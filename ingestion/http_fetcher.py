import httpx


class HTTPFetchError(Exception):
    """Raised when a website cannot be retrieved normally."""


class HTTPFetcher:
    """
    Retrieves raw HTML using a normal HTTP client.

    This class does NOT parse HTML.
    """

    DEFAULT_TIMEOUT = 20.0

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    async def fetch(self, url: str) -> str:
        """
        Fetch raw HTML.

        Raises:
            HTTPFetchError:
                If the request fails or does not return HTML.
        """

        if not url.startswith(("http://", "https://")):
            raise HTTPFetchError(
                "URL must start with http:// or https://"
            )

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=self.DEFAULT_TIMEOUT,
                headers=self.DEFAULT_HEADERS,
            ) as client:

                response = await client.get(url)

        except httpx.RequestError as exc:
            raise HTTPFetchError(
                f"Unable to retrieve website: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise HTTPFetchError(
                f"Website returned HTTP {response.status_code}"
            )

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        # Don't try to feed PDFs, images, etc. to BeautifulSoup.
        if (
            "text/html" not in content_type
            and "application/xhtml+xml"
            not in content_type
        ):
            raise HTTPFetchError(
                f"URL did not return HTML "
                f"(Content-Type: {content_type})"
            )

        return response.text