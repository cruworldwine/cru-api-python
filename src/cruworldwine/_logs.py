from __future__ import annotations

import logging
import os

logger = logging.getLogger('cruworldwine')
logger.addHandler(logging.NullHandler())

_LEVELS = {'debug': logging.DEBUG, 'info': logging.INFO}
_HANDLER_NAME = 'cruworldwine-stderr'


def setup_logging() -> None:
    """Log to stderr when the CRU_LOG environment variable is debug or info.

    Without CRU_LOG the SDK only logs through logging.getLogger('cruworldwine'), which the
    application configures as it likes. Nothing logged ever holds a credential, a token or a body.
    """
    level = _LEVELS.get(os.environ.get('CRU_LOG', '').strip().lower())
    if level is None:
        return
    if not any(h.get_name() == _HANDLER_NAME for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.set_name(_HANDLER_NAME)
        handler.setFormatter(logging.Formatter('[%(asctime)s %(levelname)s %(name)s] %(message)s'))
        logger.addHandler(handler)
    logger.setLevel(level)
