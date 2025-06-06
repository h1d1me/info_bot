import re


def safe_html(text: str) -> str:
    """Escape "<" and ">" symbols that are not a part of a tag."""
    return re.sub(
        pattern='<(?!(/|b>|i>|u>|s>|tg-spoiler>|a>|a href=|code>|pre>|code class=))',
        repl='&lt;',
        string=text,
    )
