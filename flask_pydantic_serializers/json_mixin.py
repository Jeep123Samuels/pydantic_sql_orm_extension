import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.inspection import inspect as sa_inspect


class OutputMixin(object):
    RELATIONSHIPS_TO_DICT = False
    
    def __iter__(self):
        return self.to_dict().items()
    
    def to_dict(self, include_hybrid=False, rel=None):
        if rel is None:
            rel = self.RELATIONSHIPS_TO_DICT
        res = {
            column.key: getattr(self, attr)
            for attr, column in self.__mapper__.c.items()
        }
        
        if rel:
            for attr, relation in self.__mapper__.relationships.items():
                
                # We are assuming 1-level nested objects for now
                # Will need to expand for more then 1-level backref objects.
                value = getattr(self, attr)
                if value is None:
                    res[relation.key] = None
                elif isinstance(value.__class__, DeclarativeMeta):
                    res[relation.key] = value.to_dict(rel=False)
                else:
                    res[relation.key] = [i.to_dict(rel=False) for i in value]
        
        if include_hybrid:
            for b in sa_inspect(self.__class__).all_orm_descriptors:
                if isinstance(b, hybrid_property):
                    res[b.__name__] = getattr(self, b.__name__)
        return res
    
    def to_json(self, include_hybrid=False, rel=None):
        def extended_encoder(x):
            if isinstance(x, datetime):
                return x.isoformat()
            elif isinstance(x, date):
                return x.isoformat()
            elif isinstance(x, Decimal):
                return float(x)
            elif isinstance(x, Enum):
                return x.value
        
        if rel is None:
            rel = self.RELATIONSHIPS_TO_DICT
        return json.loads(
            json.dumps(
                self.to_dict(include_hybrid=include_hybrid, rel=rel),
                default=extended_encoder,
            )
        )
