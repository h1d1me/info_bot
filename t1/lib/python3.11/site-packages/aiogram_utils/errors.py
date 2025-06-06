import logging
from contextlib import contextmanager


@contextmanager
def suppress(*exceptions, logger: logging.Logger = None, **log_kwargs):
    try:
        yield
    except exceptions as e:
        if logger:
            logger.exception(f'{e} | {log_kwargs}')
