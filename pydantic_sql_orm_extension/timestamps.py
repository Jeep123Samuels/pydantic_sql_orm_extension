from sqlalchemy import Column, func
from sqlalchemy.types import DateTime


class CreatedTimeStamps(object):
    """Base class for all asset models."""
    
    created_time = Column(DateTime, server_default=func.now())
    modified_time = Column(DateTime, server_default=func.now(), onupdate=func.current_timestamp())
