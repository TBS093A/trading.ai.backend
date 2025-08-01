from .minio import MinIOStorage
from .local import LocalStorage

__all__ = [
    "MinIOStorage",
    "LocalStorage"
] 