from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass
class HTMLQualityResult:
    """
    Result of checking whether downloaded HTML
    appears to be a usable webpage.
    """

    usable: bool
    reason: str
    text_length: int
    html_length: int


class HTMLQualityChecker:
    """
    Determines whether raw HTML is useful enough to
    continue with normal HTML processing.

    This is NOT a security/bot bypass.

    It simply identifies responses that are probably
    challenge/block/error pages.
    """

    BLOCK_INDICATORS = [
        "access denied",
        "forbidden",
        "verify you are human",
        "verify you are a human",
        "checking your browser",
        "checking your browser before accessing",
        "just a moment",
        "attention required",
        "cf-chl",
        "cloudflare",
        "captcha",
        "enable javascript and cookies",
        "unusual traffic",
        "bot detection",
    ]

    MIN_HTML_LENGTH = 500

    MIN_TEXT_LENGTH = 100

    def check(self, html: str) -> HTMLQualityResult:
        """
        Inspect HTML and determine whether it appears usable.
        """

        if not html or not html.strip():
            return HTMLQualityResult(
                usable=False,
                reason="Empty HTML response.",
                text_length=0,
                html_length=0,
            )

        html_length = len(html)

        if html_length < self.MIN_HTML_LENGTH:
            return HTMLQualityResult(
                usable=False,
                reason="HTML response is unusually small.",
                text_length=0,
                html_length=html_length,
            )

        soup = BeautifulSoup(
            html,
            "lxml",
        )

        # Remove things that don't represent visible page text.
        for tag in soup.find_all(
            [
                "script",
                "style",
                "noscript",
                "svg",
            ]
        ):
            tag.decompose()

        text = soup.get_text(
            separator=" ",
            strip=True,
        )

        text = " ".join(text.split())

        text_lower = text.lower()

        for indicator in self.BLOCK_INDICATORS:
            if indicator in text_lower:
                return HTMLQualityResult(
                    usable=False,
                    reason=(
                        f"Possible bot/challenge page detected: "
                        f"{indicator}"
                    ),
                    text_length=len(text),
                    html_length=html_length,
                )

        if len(text) < self.MIN_TEXT_LENGTH:
            return HTMLQualityResult(
                usable=False,
                reason=(
                    "HTML contains too little visible text."
                ),
                text_length=len(text),
                html_length=html_length,
            )

        return HTMLQualityResult(
            usable=True,
            reason="HTML appears usable.",
            text_length=len(text),
            html_length=html_length,
        )