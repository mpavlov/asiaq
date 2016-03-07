'''Utility function for logging'''
import logging
import sys


def configure_logging(debug):
    '''Sets the default logger and the boto logger to appropriate levels of chattiness.'''
    logger = logging.getLogger('')
    boto_logger = logging.getLogger('boto')
    botocore_logger = logging.getLogger('botocore')
    if debug:
        logger.setLevel(logging.DEBUG)
        boto_logger.setLevel(logging.INFO)
        botocore_logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
        boto_logger.setLevel(logging.CRITICAL)
        botocore_logger.setLevel(logging.CRITICAL)

    stream_handler = logging.StreamHandler(sys.__stdout__)
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s'))
    logger.addHandler(stream_handler)
