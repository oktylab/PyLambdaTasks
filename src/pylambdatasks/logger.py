import logging, os, sys

logger = logging.getLogger("pylambdatasks")

if os.environ.get("PYLAMBDATASKS_DEBUG") == "1":
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("[PyLambdaTasks] %(message)s")
    handler.setFormatter(formatter)
    
    if logger.hasHandlers():
        logger.handlers.clear()
        
    logger.addHandler(handler)
    logger.propagate = False
else:
    logger.addHandler(logging.NullHandler())